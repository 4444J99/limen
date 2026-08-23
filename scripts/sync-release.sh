#!/usr/bin/env bash
# sync-release.sh — the SUBSTRATE SELF-HEAL organ. Closes the self-* loop: root → leaf → root.
#
# Every few beats it re-converges the live daemon checkout to the release (origin/main):
#   • CODE follows the release automatically — a push to origin/main IS a deploy (push is retired
#     as a lever; continuous deployment). All organ scripts + the cli package update in place and
#     take effect for the very next subprocess the beat spawns.
#   • DATA follows the remote owner — tasks.yaml is a read-only local cache. This organ never
#     copies, restores, checks out, or preserves a locally mutated board across a release change.
#   • It FAILS OPEN, always — fast-forward ONLY, never force / reset / merge-commit; on a diverged
#     history or a blocked tree it logs the cheapest path and returns 0 so the beat never stops
#     (the "never a silent no" invariant). It NEVER exits or re-execs the daemon (KeepAlive=false:
#     an exit would not respawn — that is the documented dead-daemon failure mode).
#   • HEAD RESTS ON THE RELEASE BRANCH — a checkout parked on a work branch is UNPARKED back to
#     the release, but only when provably loss-free (branch tip safe on origin + no tracked dirt
#     beyond generated cache drift); see the unpark valve below. When ANOTHER WORKTREE holds the
#     branch name, git refuses the switch and the valve DETACHES at origin/$BRANCH instead: the
#     fleet needs the release CODE, not the NAME, and detaching needs nothing from the other
#     worktree. That is a contingency, not a resting state — the re-attach valve returns HEAD to
#     the branch the moment the name is free again.
#
# Untracked runtime state (logs/autonomy-policy.json governor gate, usage.json, caches) is SAFE:
# a fast-forward only advances committed history and leaves untracked files untouched. This organ
# deliberately does NOT `git add -A` (that is what once swept the governor gate into a commit).
set -uo pipefail
export HOME="${HOME:-/Users/4jp}"
ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
BRANCH="${LIMEN_RELEASE_BRANCH:-main}"

# THE ORGAN'S OWN REPOSITORY ROOT — where THIS script lives, which is not necessarily the tree it
# operates on. Normally they are the same directory and nothing below behaves differently.
#
# They diverge in exactly one situation, and it is the one that matters: BOOTSTRAPPING A WEDGED
# TREE. This organ is the only thing that advances $ROOT, so when a fix to the organ itself is
# needed to unwedge $ROOT, that fix cannot arrive by the usual route — the tree that needs the new
# code is the tree the new code exists to update. The escape is to run a CURRENT copy of the organ
# (from a worktree at origin/main) against the stale $ROOT. That already worked for the organ's own
# logic, because bash reads this file from where it was invoked. It did NOT work for the organ's
# HELPERS: they were resolved from "$ROOT", so a current organ still asked the STALE tree's probe
# for its verdict and got the stale answer back — which is precisely the two-rail confusion the
# repo's verify recipe warns about, appearing inside a single script.
#
# Measured 2026-08-12: a current organ, run against a live checkout 29 commits behind, correctly
# proved the divergence loss-free and then declined anyway, because $ROOT's OLD occupancy classifier
# reported a ChatGPT.app stdio server as an interactive session. The organ's fix and the probe's fix
# were both already merged and green; neither could be reached. A tool must use ITS OWN libraries
# and only take the TARGET from its argument.
SELF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd -P)" || SELF_ROOT="$ROOT"
[ -n "$SELF_ROOT" ] || SELF_ROOT="$ROOT"

# Regenerable daemon bookkeeping — receipt files the beat REWRITES every cycle. A commit touching ONLY
# these is "unique" by patch-id yet carries NO genuine work: it is loss-free to re-converge past. This
# is the exact commit that otherwise strands the live checkout — a receipt committed while in sync, then
# left diverged when origin advanced (a merged PR) before its push landed → ff-only fails open forever,
# pinning the daemon to stale code. Distinct from the patch-id valve ("already upstream"): this is
# "regenerable, so losing it costs nothing". Override the globs via LIMEN_SYNC_RECEIPT_GLOBS.
# tasks.yaml belongs here by this organ's own DATA doctrine (header): the board file is a read-only
# local cache of the keeper's projection — never preserved across a release change; TABVLARIVS
# republishes it every beat and the collapse guard restores from the projection branch. Observed
# park this closes: a local-only "fix validation errors in tasks.yaml" commit (2026-07-19) pinned
# the live checkout 60 commits behind for 3 days of loud fail-open beats.
RECEIPT_GLOBS="${LIMEN_SYNC_RECEIPT_GLOBS:-tasks.yaml docs/worktree-preservation-receipts.json docs/pr-receipts.json docs/*-receipts.json docs/*-receipt.json docs/receipts/*.json docs/receipts/*/*.json logs/overnight-watch.md docs/branch-hygiene.md docs/always-working.md docs/capacity-fill.md docs/dispatch-health.md docs/diurnal/INDEX.md docs/github-*.json organs/contributions/* organs/financial/* docs/RECLASSIFY-PROPOSAL.md}"
_only_receipts() {  # exit 0 ⟺ stdin has ≥1 path AND every path matches a receipt glob
  local f p matched any=0
  local -a globs
  read -r -a globs <<<"$RECEIPT_GLOBS"   # split on whitespace WITHOUT pathname-expanding the globs
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    any=1; matched=0
    for p in "${globs[@]}"; do
      # shellcheck disable=SC2254  # $p is an intentional case glob-pattern, not a literal to quote
      case "$f" in $p) matched=1; break ;; esac
    done
    [ "$matched" = 1 ] || return 1
  done
  [ "$any" = 1 ]
}

# _paths_identical_upstream <base> <local> <remote>
# exit 0 ⟺ every path the local-only commits touch resolves to the SAME blob at <local> and
# <remote> (or is absent from both) — i.e. the bytes are ALREADY upstream, so `reset --hard
# <remote>` provably discards no committed content.
#
# Why this exists beside the patch-id valve: patch-id hashes a commit's WHOLE diff, so it only
# recognises the content as upstream when the upstream commit changed exactly the same set of
# files. The common real case is the same content landing upstream bundled inside a LARGER
# commit — measured 2026-08-12, a 2-file local commit (docs/ci-red-disposition-*, +141) against
# the byte-identical files inside a 24-file release commit (+1684/-594) hashed differently, so
# valve 1 declared "genuinely unique work" and the organ fail-opened protecting content origin
# already had. Nothing about those two facts ever changes, so that wedge is PERMANENT: the live
# checkout sat 29 behind while every beat re-printed the same loud notice, and the fleet executed
# stale code — including merged fixes whose gates were all green.
#
# Content identity is the question the reset actually poses ("would this lose anything?"), and it
# is decided per PATH, not per commit. Strictly narrower than it looks: a local commit that
# deletes a file origin still has, or adds one origin lacks, compares unequal and still fails
# open. An empty changed-path set returns 1 — absence of paths is not evidence of safety.
_paths_identical_upstream() {
  local base="$1" lref="$2" rref="$3" f a b any=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    any=1
    a="$(git rev-parse --quiet --verify "$lref:$f" 2>/dev/null || echo absent)"
    b="$(git rev-parse --quiet --verify "$rref:$f" 2>/dev/null || echo absent)"
    [ "$a" = "$b" ] || return 1
  done <<EOF
$(git diff --name-only "$base..$lref" 2>/dev/null)
EOF
  [ "$any" = 1 ]
}

# exit 0 ⟺ $BRANCH is checked out in some OTHER worktree of this repository — the one refusal git
# raises that no amount of tidying THIS tree can clear, because the obstacle is not here.
#
# Derived STRUCTURALLY from `git worktree list --porcelain`, never by matching git's refusal text.
# That text is not stable across versions ("is already checked out at" / "is already used by
# worktree at") and it is localised, so a string match would silently stop recognising the case on
# a git upgrade — failing back to the fail-open branch, which looks exactly like normal operation.
# Paths are compared physically (`pwd -P`): $ROOT commonly reaches the repo through a symlink, and
# a textual compare would then read the live root as "some other worktree" and detach against
# itself.
_branch_held_elsewhere() {
  local wt="" line root_p wt_p
  root_p="$(cd "$ROOT" 2>/dev/null && pwd -P)" || return 1
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) wt="${line#worktree }" ;;
      "branch refs/heads/$BRANCH")
        wt_p="$(cd "$wt" 2>/dev/null && pwd -P)" || wt_p="$wt"
        [ "$wt_p" = "$root_p" ] || return 0
        ;;
    esac
    # `git -C "$ROOT"`, not bare git: --census answers from wherever it was invoked and never cd's,
    # so a cwd-dependent helper would be correct on two of its three call sites and quietly wrong on
    # the third — reporting "nobody holds it" from outside the repo, which is the answer that
    # disables the whole valve.
  done < <(git -C "$ROOT" worktree list --porcelain 2>/dev/null)
  return 1
}

if [ "${1:-}" = "--census" ]; then
  # Computed in SHELL and passed in, rather than re-derived in the heredoc: two implementations of
  # "who holds the branch" is two things that can disagree, and the one that decides (the valve)
  # would not be the one a reader is looking at (the census). Same reason the retirement denominator
  # got extracted to a single predicate.
  census_held=false
  _branch_held_elsewhere && census_held=true
  python3 - "$ROOT" "$BRANCH" "$RECEIPT_GLOBS" "$census_held" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
branch = sys.argv[2]
receipt_globs = [item for item in sys.argv[3].split() if item]
branch_held_elsewhere = sys.argv[4] == "true" if len(sys.argv) > 4 else False


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def count_lines(proc: subprocess.CompletedProcess[str]) -> int:
    if proc.returncode != 0:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


inside = git("rev-parse", "--is-inside-work-tree")
is_repo = inside.returncode == 0 and inside.stdout.strip() == "true"
tracked_dirty = git("diff", "--name-only", "HEAD") if is_repo else subprocess.CompletedProcess([], 1, "", "")
cached_dirty = git("diff", "--cached", "--name-only") if is_repo else subprocess.CompletedProcess([], 1, "", "")
untracked = git("ls-files", "--others", "--exclude-standard") if is_repo else subprocess.CompletedProcess([], 1, "", "")
current = git("symbolic-ref", "--quiet", "--short", "HEAD") if is_repo else subprocess.CompletedProcess([], 1, "", "")
remote = git("rev-parse", f"origin/{branch}") if is_repo else subprocess.CompletedProcess([], 1, "", "")

print(
    json.dumps(
        {
            "root_present": root.exists(),
            "git_repo": is_repo,
            "on_release_branch": bool(current.stdout.strip() == branch) if is_repo else False,
            # Without this field a detached-at-the-release root reports on_release_branch=false and
            # says nothing about WHY — indistinguishable in the census from a genuine park, which is
            # the state it is the converged answer to.
            "detached_head": bool(is_repo and not current.stdout.strip()),
            "branch_held_elsewhere": branch_held_elsewhere,
            "remote_tracking_present": remote.returncode == 0,
            "tracked_dirty_count": count_lines(tracked_dirty),
            "cached_dirty_count": count_lines(cached_dirty),
            "untracked_count": count_lines(untracked),
            "tasks_present": (root / "tasks.yaml").exists(),
            "logs_present": (root / "logs").exists(),
            "sync_collision_present": (root / "logs" / ".sync-collision").exists(),
            "loop_update_pending": (root / "logs" / ".loop-update-pending").exists(),
            "receipt_globs": len(receipt_globs),
        },
        indent=2,
        sort_keys=True,
    )
)
PY
  exit 0
fi

# --check: a real predicate (unlike --census, which is always exit 0 and informational) — exit 0
# ⟺ the live root RESTS ON the release branch, HEAD is exactly origin/$BRANCH, and every tracked
# or untracked dirty path is regenerable daemon bookkeeping (the same RECEIPT_GLOBS / _only_receipts
# tolerance this organ already trusts for its own reconcile valve at the patch-id check below —
# routed through one canonical surface rather than a second hand-rolled dirty-tree definition).
if [ "${1:-}" = "--check" ]; then
  cd "$ROOT" 2>/dev/null || { echo "sync-release --check: FAIL — no LIMEN_ROOT ($ROOT)"; exit 1; }
  git rev-parse --git-dir >/dev/null 2>&1 || { echo "sync-release --check: FAIL — not a git repo"; exit 1; }
  git fetch --quiet origin "$BRANCH" 2>/dev/null || { echo "sync-release --check: FAIL — fetch failed"; exit 1; }
  CUR="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo)"
  detached_ok=0
  if [ "$CUR" != "$BRANCH" ]; then
    # DETACHED AT THE RELEASE, while another worktree legitimately holds the branch name, is the
    # converged state under contention — not a park. What this predicate asserts is that the live
    # root RUNS the release; the branch name is the ordinary means to that, not the end, and there
    # is no version of this check that both demands the name and can ever go green while a second
    # worktree holds it. The HEAD==origin/$BRANCH comparison below is UNCHANGED and still fails a
    # detach at a stale commit, so this arm cannot launder a behind checkout — it only stops
    # calling the contended-but-current one a failure. A gratuitous detach (name free) still FAILs.
    if [ -n "$CUR" ] || ! _branch_held_elsewhere; then
      echo "sync-release --check: FAIL — on '${CUR:-detached}' not '$BRANCH'"; exit 1
    fi
    detached_ok=1
  fi
  LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
  REMOTE="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo)"
  if [ -z "$REMOTE" ] || [ "$LOCAL" != "$REMOTE" ]; then
    echo "sync-release --check: FAIL — HEAD ${LOCAL:0:7} != origin/$BRANCH ${REMOTE:0:7}"; exit 1
  fi
  dirty="$( { git diff --name-only HEAD 2>/dev/null; git diff --cached --name-only 2>/dev/null; \
              git ls-files --others --exclude-standard 2>/dev/null; } | sort -u)"
  if [ -n "$dirty" ] && ! printf '%s\n' "$dirty" | _only_receipts; then
    echo "sync-release --check: FAIL — non-receipt dirt: $(printf '%s' "$dirty" | tr '\n' ' ')"; exit 1
  fi
  if [ "$detached_ok" = 1 ]; then
    echo "sync-release --check: PASS — live root DETACHED at exact origin/$BRANCH and clean (or receipts-only); branch name held by another worktree"
    exit 0
  fi
  echo "sync-release --check: PASS — live root exact origin/$BRANCH and clean (or receipts-only)"
  exit 0
fi

cd "$ROOT" 2>/dev/null || { echo "sync-release: no LIMEN_ROOT ($ROOT) — fail open"; exit 0; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "sync-release: not a git repo — fail open"; exit 0; }

# LIMEN_RELEASE_BRANCH selects the convergence target; it is not authority to
# reinterpret the repository's actual default branch as a disposable parked
# topic branch. Resolve origin/HEAD independently and refuse before any
# preservation commit or push when an override would otherwise make the real
# default branch enter the unpark path.
DEFAULT_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
if [ -z "$DEFAULT_BRANCH" ]; then
  DEFAULT_BRANCH="$(git ls-remote --symref origin HEAD 2>/dev/null \
    | awk '$1 == "ref:" && $2 ~ /^refs\/heads\// { sub(/^refs\/heads\//, "", $2); print $2; exit }')"
fi
[ -n "$DEFAULT_BRANCH" ] || DEFAULT_BRANCH="main"
CUR="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo)"
if [ -n "$CUR" ] && [ "$CUR" = "$DEFAULT_BRANCH" ] && [ "$BRANCH" != "$DEFAULT_BRANCH" ]; then
  echo "sync-release: REFUSED — '$CUR' is origin's default branch; LIMEN_RELEASE_BRANCH='$BRANCH' cannot reclassify or push it"
  exit 0
fi

git fetch --quiet origin "$BRANCH" 2>/dev/null || { echo "sync-release: fetch failed — fail open"; exit 0; }
LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
REMOTE="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo)"
[ -n "$REMOTE" ] || { echo "sync-release: no origin/$BRANCH — fail open"; exit 0; }

# A dirty local board is neither a release artifact nor authority to overwrite the GitHub-backed
# projection. Leave it byte-identical and require authenticated cache hydration.
if ! git diff --quiet -- tasks.yaml 2>/dev/null \
   || ! git diff --cached --quiet -- tasks.yaml 2>/dev/null; then
  echo "sync-release: local tasks.yaml cache is dirty — refusing to copy/restore/discard it; hydrate from the authenticated keeper"
  exit 0
fi

# ── SESSION-CONTENTION guard (IF-SESSION-NON-CONTENTION) ────────────────────────────────────────
# The ideal: "the fleet never rebases or cleans the tree a live session is working in." This organ
# is the one remaining path that could — dispatch already preserves-and-retries rather than reusing
# an existing worktree, and reclaim-worktrees.py is liveness-gated on its delete path. Only the LIVE
# CHECKOUT was unguarded, and it is the tree a session is most likely to be sitting in by mistake.
#
# Probed ONCE, consulted at each destructive site. The probe reports an interactive agent session
# whose cwd is in TRACKED ground of the live checkout, excluding nested worktrees (isolated by
# design), gitignored runtime, and this process's own lineage. It FAILS OPEN: an unavailable probe
# yields an empty OCCUPANT and every valve behaves exactly as before, honouring this script's own
# capitalised contract ("It FAILS OPEN, always").
#
# PRECEDENCE, stated once: a clean FAST-FORWARD is never blocked. IF-LIVE-TREE-COHERENCE wins there,
# because a silently-never-converging sync is a failure this fleet has already paid for (120 commits
# behind, six days stale, nothing read the log). Only the DESTRUCTIVE valves — unpark, reset --hard,
# stash push — defer to a live session, because those are the ones that can take work away.
OCCUPANT=""
if [ "${LIMEN_SESSION_CONTENTION_GUARD:-1}" = "1" ]; then
  # CAPTURE AND EXTRACT ARE SEPARATE STEPS, and that is not style. `probe` exits 1 when the tree
  # is OCCUPIED — that is its verdict, not a failure — and this file runs under `set -o pipefail`
  # (top), which propagates that 1 out of the pipeline. Written as
  #     OCCUPANT="$(probe | sed ...)" || OCCUPANT=""
  # the fallback therefore fired on exactly the branch that had found something, blanking the pid
  # it had just extracted: the trace reads `OCCUPANT=34598` followed immediately by `OCCUPANT=`.
  # The guard could not arm in either direction — free left it empty, occupied ALSO left it empty
  # — so it shipped inert and every gate stayed green. A defensive `||` became an eraser.
  # `|| true` absorbs the intended non-zero; the sed then reads a variable, where no exit status
  # of the probe's can reach it. The TEXT is the verdict here, never the status.
  # SELF_ROOT for the helper, $ROOT for the TARGET (see SELF_ROOT above). LIMEN_ROOT is passed
  # explicitly because session-contention.py resolves its own `limen` package from it — without
  # that, the current script would still import the stale tree's classifier and get its verdict.
  _probe_out="$(LIMEN_ROOT="$SELF_ROOT" python3 "$SELF_ROOT/scripts/session-contention.py" \
    probe --root "$ROOT" 2>/dev/null || true)"
  OCCUPANT="$(printf '%s\n' "$_probe_out" | sed -n 's/.*OCCUPIED by pid \([0-9][0-9]*\).*/\1/p')"
  # A BLIND PROBE MUST NOT BE A QUIET ONE. The capture above swallows the probe's stdout, so on a
  # host where the probe cannot run — package unimportable, lsof missing — the guard disarms and
  # this beat says nothing whatsoever about it. Fail-open is correct and unchanged (OCCUPANT stays
  # empty either way); being unable to tell the two apart in the log is not, and is the same
  # "silent no" this organ's header exists to prevent. One line, only on the blind path.
  case "$_probe_out" in
    *"probe UNAVAILABLE"*)
      echo "sync-release: session-contention probe UNAVAILABLE — guard DISARMED, proceeding fail-open (IF-SESSION-NON-CONTENTION unverified this beat)"
      ;;
  esac
fi

# Returns 0 (true) when a live session holds the tree, after logging and recording the incident.
# Recording is best-effort by construction: this runs inside the beat and must never stop it.
_contended() {
  [ -n "$OCCUPANT" ] || return 1
  echo "sync-release: live session (pid $OCCUPANT) occupies $ROOT — declining $1 (IF-SESSION-NON-CONTENTION)"
  python3 "$ROOT/scripts/session-contention.py" record --root "$ROOT" --pid "$OCCUPANT" --action "$1" \
    >/dev/null 2>&1 || true
  return 0
}

# ── UNPARK valve — the live checkout must REST ON THE RELEASE BRANCH. A session that leaves HEAD
# parked on a work branch strands the daemon on stale code with no way home (observed
# 2026-06-29 → 07-04: five days pinned to a jules-capfill branch, 65 behind release, every
# autonomic capture entangling runtime state into that branch — because the valve fail-opened on
# dirt and merely HOPED capture.sh would land it "next beat"; for five days nothing did).
# PRESERVE-THEN-UNPARK (the operator's standing rule: nothing is abandoned that is not first safe on
# origin): the valve no longer depends on capture.sh's ordering — it lands the parked branch's own
# work to origin ITSELF (commits tracked dirt onto the branch, pushes the tip), THEN rests HEAD on
# the release. tasks.yaml must already be a clean remote-owned cache. The ONLY fail-open is a push
# that genuinely fails (offline/auth) — because then the work is not yet preserved and switching
# away would lose it.
#
# ── RE-ATTACH valve — the mirror of the detach fallback at the bottom of the unpark block, and the
# reason that fallback is a contingency rather than a one-way door. A detached live root is this
# organ's answer to a held branch NAME, never its resting state, so the moment the name is free HEAD
# comes home to it. Without this arm the first contention would detach the checkout permanently and
# "HEAD RESTS ON THE RELEASE BRANCH" would survive only in its weakened detached form — the same
# never-converging shape as the park, arrived at from the other side.
#
# Two conditions beyond "the name is free", both narrowing what re-attaching can cost:
#   • the local branch REF must have no unique work (ancestor of origin/$BRANCH). Re-attaching to a
#     diverged local branch would trade a detached-but-current HEAD for an attached-and-diverged one,
#     which the ff below can only fail open on — strictly worse than staying detached.
#   • it is a destructive valve (it moves HEAD in a tree a session may hold), so it defers to the
#     contention guard exactly like unpark, reset --hard, and stash push.
# The ff below then advances the re-attached branch normally; this valve only restores the name.
if [ -z "$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo)" ] \
   && ! _branch_held_elsewhere \
   && git rev-parse --verify --quiet "refs/heads/$BRANCH" >/dev/null 2>&1 \
   && git merge-base --is-ancestor "refs/heads/$BRANCH" "origin/$BRANCH" 2>/dev/null; then
  if ! _contended "skipped-reattach"; then
    if git switch --quiet "$BRANCH" 2>/dev/null; then
      LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
      echo "sync-release: RE-ATTACHED detached HEAD → '$BRANCH' ✓ (branch name free again)"
    fi
  fi
fi

CUR="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo)"
if [ -n "$CUR" ] && [ "$CUR" != "$BRANCH" ]; then
  # Unpark commits the session's dirt, pushes it, and switches HEAD out from under them. Every
  # step of that is a rewrite of the tree they are working in.
  _contended "skipped-unpark" && exit 0
  git fetch --quiet origin "$CUR" 2>/dev/null || true
  dirt="$( { git diff --name-only HEAD 2>/dev/null; git diff --cached --name-only 2>/dev/null; } | grep -vxF 'tasks.yaml' | sort -u)"
  if [ -n "$dirt" ]; then
    # Stage ONLY tracked modifications (never untracked — no new secret can ride in; untracked
    # release-collisions are handled by the backup sweep below) and preserve them onto the branch.
    printf '%s\n' "$dirt" | while IFS= read -r f; do [ -n "$f" ] && git add -- "$f" 2>/dev/null || true; done
    git commit --quiet -m "capture(sync-release): preserve parked dirt before unpark [skip ci]" 2>/dev/null || true
    LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
  fi
  # Push the branch tip to origin if it is not already there — the valve preserves it itself rather
  # than waiting a beat. Only when the tip is provably safe on origin do we proceed to switch.
  RCUR="$(git rev-parse "origin/$CUR" 2>/dev/null || echo)"
  if [ "$RCUR" != "$LOCAL" ]; then
    if git push --quiet origin "$CUR" 2>/dev/null; then
      git fetch --quiet origin "$CUR" 2>/dev/null || true
      RCUR="$(git rev-parse "origin/$CUR" 2>/dev/null || echo)"
    fi
  fi
  if [ -z "$RCUR" ] || [ "$RCUR" != "$LOCAL" ]; then
    echo "sync-release: parked on '$CUR' — could not preserve tip to origin (offline/auth?) — fail open (work kept local, valve retries next beat)"
    exit 0
  fi
  # A switch is blocked by exactly what blocks the ff below (observed on the 2026-07-04 live heal):
  # (a) an UNTRACKED file the release now TRACKS (censor/precedents.jsonl that day) — release-owned,
  # so back it up to logs/.sync-collision and remove it, the same invariant as the ff collision
  # valve. A branch already checked out in another worktree also refuses; that stays fail-open
  # (surfaced in the message). The dirty-cache guard above keeps tasks.yaml out of this repair path.
  release_tracked="$(git ls-tree -r --name-only "origin/$BRANCH" 2>/dev/null || echo)"
  untracked="$(git ls-files --others --exclude-standard 2>/dev/null || echo)"
  BK="$ROOT/logs/.sync-collision"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    printf '%s\n' "$release_tracked" | grep -qxF "$f" || continue   # only paths the release tracks
    mkdir -p "$BK/$(dirname "$f")" 2>/dev/null || true
    cp -f "$f" "$BK/$f" 2>/dev/null || true                         # back up (never delete) before removing
    rm -f "$f" 2>/dev/null || true
  done <<UNPARK_EOF
$untracked
UNPARK_EOF
  unparked=0
  why="$(git switch --quiet "$BRANCH" 2>&1)" && unparked=1
  if [ "$unparked" = 1 ]; then
    LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
    echo "sync-release: UNPARKED '$CUR' → '$BRANCH' (branch tip safe on origin/$CUR) ✓"
  # ── DETACH fallback. Git's constraint is that a branch NAME cannot be checked out twice; it has no
  # objection whatsoever to the COMMIT. So when the refusal is another worktree holding the name —
  # and only then — take the release by SHA instead. This asks nothing of the other worktree: no
  # file it holds is touched, nothing is removed, and it keeps working on exactly the tree it had.
  #
  # This arm exists because the alternative was a sensor with no effector. The organ already
  # captured the refusal reason (git's message literally names the holding worktree) and then did
  # nothing but ask a human, every beat, forever — while the park FED ITSELF: unpark stays blocked,
  # so the daemon keeps committing captures onto the parked branch (21 of them, all `capture:`, over
  # one day, live checkout three merges stale). Fail-open was the right default and the wrong
  # terminus.
  #
  # Loss-free by construction: the preserve-then-push above has already proven the parked branch tip
  # is safe on origin/$CUR, and this only moves HEAD to a commit origin already has. The re-attach
  # valve above returns HEAD to the branch once the name is free, so this is a contingency the organ
  # exits on its own — not a state it has to be rescued from.
  elif _branch_held_elsewhere && git switch --quiet --detach "origin/$BRANCH" 2>/dev/null; then
    LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
    echo "sync-release: UNPARKED '$CUR' → DETACHED at origin/$BRANCH ${LOCAL:0:7} ✓ (branch name held by another worktree — the fleet needs the release CODE, not the NAME)"
  else
    why="$(printf '%s' "$why" | head -2 | tr '\n' ' ' | cut -c1-200)"
    echo "sync-release: switch '$CUR' → '$BRANCH' refused (${why}) — fail open (reconcile by hand)"
    exit 0
  fi
fi

[ "$LOCAL" = "$REMOTE" ] && { echo "sync-release: at release ${REMOTE:0:7} ✓"; exit 0; }

# fast-forward ONLY — never touch a diverged or rewound history…
if ! git merge-base --is-ancestor "$LOCAL" "$REMOTE" 2>/dev/null; then
  # …EXCEPT the one provably-safe divergence: every local-only commit is ALREADY on origin by
  # content (git patch-id). That is the observed "session redid work that already landed" drift
  # (e.g. the Studium Odyssey commits replayed on a stale checkout). No unique work exists to lose,
  # so re-converging to the release is loss-free. We still NEVER force-move when ANY local commit
  # is genuinely unique — that path stays fail-open + hand-reconcile (the live-checkout-chaos guard).
  BASE="$(git merge-base "$LOCAL" "$REMOTE" 2>/dev/null || echo)"
  unique=1
  if [ -n "$BASE" ]; then
    unique=0
    upstream_ids="$(git log --no-merges --format=%H "$BASE..$REMOTE" 2>/dev/null \
      | while read -r h; do git show "$h" 2>/dev/null | git patch-id --stable 2>/dev/null | cut -d' ' -f1; done)"
    while read -r h; do
      [ -n "$h" ] || continue
      pid="$(git show "$h" 2>/dev/null | git patch-id --stable 2>/dev/null | cut -d' ' -f1)"
      [ -n "$pid" ] || { unique=1; break; }                       # empty diff / unknown ⇒ treat as unique (safe)
      printf '%s\n' "$upstream_ids" | grep -qxF "$pid" || { unique=1; break; }
    done <<EOF
$(git log --no-merges --format=%H "$BASE..$LOCAL" 2>/dev/null)
EOF
  fi
  reconcile_reason="all local commits already upstream (patch-id)"
  # Second loss-free valve: the unique local commits touch ONLY regenerable receipts (the beat rewrites
  # them next cycle). Guarded by --is-ancestor so we NEVER discard a commit origin doesn't already have
  # as a descendant — i.e. only when the release is strictly AHEAD of BASE, never on a rewound remote.
  if [ "$unique" = 1 ] && [ -n "$BASE" ] \
     && git merge-base --is-ancestor "$BASE" "$REMOTE" 2>/dev/null \
     && git diff --name-only "$BASE..$LOCAL" 2>/dev/null | _only_receipts; then
    unique=0
    reconcile_reason="local commit(s) touch ONLY regenerable receipts"
  fi
  # Third loss-free valve: every path the unique local commits touch is already byte-identical at
  # origin. Catches the content-landed-inside-a-larger-upstream-commit wedge that patch-id misses
  # (see _paths_identical_upstream). Same --is-ancestor guard: never on a rewound remote.
  if [ "$unique" = 1 ] && [ -n "$BASE" ] \
     && git merge-base --is-ancestor "$BASE" "$REMOTE" 2>/dev/null \
     && _paths_identical_upstream "$BASE" "$LOCAL" "$REMOTE"; then
    unique=0
    reconcile_reason="every path in the local commit(s) is already byte-identical at origin"
  fi
  CUR="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo)"
  if [ "$unique" = 0 ] && [ "$CUR" = "$BRANCH" ] && ! _contended "skipped-reset-hard"; then
    # reset --hard leaves UNTRACKED runtime (logs/, usage.json) untouched; the valve above proved no
    # genuine committed work is lost. The clean tasks.yaml cache follows the release projection.
    if git reset --hard "origin/$BRANCH" --quiet 2>/dev/null; then
      echo "sync-release: diverged but ${reconcile_reason} — re-converged ${LOCAL:0:7} → ${REMOTE:0:7} ✓ (no unique work lost)"
      exit 0
    fi
  fi
  echo "sync-release: local (${LOCAL:0:7}) diverged from origin/$BRANCH (${REMOTE:0:7}) with UNIQUE local work — fail open"
  echo "sync-release: cheapest path = reconcile by hand (this organ NEVER force-moves genuinely-unique history)"
  exit 0
fi
CUR="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo)"
if [ "$CUR" != "$BRANCH" ]; then
  # DETACHED AT THE RELEASE is a steady state, not a park (see the detach fallback in the unpark
  # valve) — and this arm is what makes it one. `git merge --ff-only` on a detached HEAD advances
  # HEAD and switches NOTHING, so the "no auto-switch" refusal below has nothing to refuse: there is
  # no branch to move. The ancestry proof above has already established there is no unique local
  # work, and the stash / collision valves below are reused unchanged rather than re-implemented for
  # this path.
  #
  # Without this the organ would unpark once and then fail open on EVERY beat afterwards — the same
  # never-converging park it just escaped, one level down and harder to see, because the log line
  # would read as an ordinary refusal rather than as a valve that fires once and dies.
  if [ -n "$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo)" ] || ! _branch_held_elsewhere; then
    echo "sync-release: on '$CUR' not '$BRANCH' — fail open (no auto-switch)"; exit 0
  fi
  echo "sync-release: DETACHED at ${LOCAL:0:7}, '$BRANCH' still held by another worktree — advancing detached HEAD to the release"
fi

# Set tracked working changes aside so the ff is not blocked by build artifacts. The dirty-cache
# guard above ensures tasks.yaml is not among them; the released projection wins.
stashed=0
if ! git diff --quiet 2>/dev/null; then
  # A dirty tree under a live session is that session's UNCOMMITTED WORK. Stashing it is exactly
  # the thing the ideal forbids — and worse than a reset, because the stack is shared across every
  # worktree on this host, so the session cannot even safely pop it back.
  # EXCEPTION: If the dirty tracked files are purely daemon-regenerable bookkeeping, they are NOT
  # session work. We stash them so the ff can proceed, and skip the contention exit.
  if ! git diff --name-only 2>/dev/null | _only_receipts; then
    _contended "skipped-stash-push" && exit 0
  fi
  git stash push --quiet 2>/dev/null && stashed=1 || true
fi

# An UNTRACKED local file that collides with a path the release now TRACKS also blocks the ff (git
# refuses to overwrite untracked files — the .claude/settings.json drift observed 2026-06-24). Those
# paths are release-owned, so the released version must win, exactly like the tracked stash-drop above.
# Back up ONLY the colliding paths (logs/.sync-collision — never deleted) and remove them so the ff can
# write the tracked version. Untracked runtime the release does NOT track (logs/, usage.json, caches,
# the governor gate) is never in this set and stays untouched — the deliberate "no git add -A" invariant.
collided=0
untracked="$(git ls-files --others --exclude-standard 2>/dev/null || echo)"
if [ -n "$untracked" ]; then
  release_tracked="$(git ls-tree -r --name-only "origin/$BRANCH" 2>/dev/null || echo)"
  BK="$ROOT/logs/.sync-collision"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    printf '%s\n' "$release_tracked" | grep -qxF "$f" || continue   # only paths the release tracks
    mkdir -p "$BK/$(dirname "$f")" 2>/dev/null || true
    cp -f "$f" "$BK/$f" 2>/dev/null || true                         # back up (never delete) before removing
    rm -f "$f" 2>/dev/null && collided=1 || true
  done <<EOF
$untracked
EOF
  [ "$collided" = 1 ] && echo "sync-release: cleared release-owned untracked file(s) blocking ff (backup: logs/.sync-collision) — release version wins"
fi

LOOP_BEFORE="$(git rev-parse "HEAD:scripts/heartbeat-loop.sh" 2>/dev/null || echo)"
if git merge --ff-only "origin/$BRANCH" --quiet 2>/dev/null; then
  [ "$stashed" = 1 ] && git stash drop --quiet 2>/dev/null || true
  echo "sync-release: ff ${LOCAL:0:7} → ${REMOTE:0:7} ✓ — release deployed (organs live next subprocess)"
  LOOP_AFTER="$(git rev-parse "HEAD:scripts/heartbeat-loop.sh" 2>/dev/null || echo)"
  if [ -n "$LOOP_BEFORE" ] && [ "$LOOP_BEFORE" != "$LOOP_AFTER" ]; then
    # the conductor's OWN loop body changed; organs are already current. Do NOT exit (KeepAlive=false
    # would leave it dead) — flag for a deliberate kickstart to load the new loop.
    touch "$ROOT/logs/.loop-update-pending" 2>/dev/null || true
    echo "sync-release: heartbeat-loop.sh changed; the resident scheduler is retired. Run: limen observe --once --scope host"
  fi
else
  [ "$stashed" = 1 ] && git stash pop --quiet 2>/dev/null || true
  echo "sync-release: ff blocked (untracked file would be overwritten?) — fail open, beat continues"
fi
exit 0
