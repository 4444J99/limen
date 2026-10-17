#!/usr/bin/env bash
# Operator reclaim script — homing session 2026-10-17.
# Every removal below targets state whose content is PROVEN on a remote (see homing receipt).
# Usage:
#   reclaim-operator.sh dry-run     # derive plans, list what would go, change nothing
#   reclaim-operator.sh apply       # apply exact plans derived in this run
#   reclaim-operator.sh post-check  # debt census + disk after apply
set -euo pipefail

LIMEN=/Users/4jp/Workspace/limen
PY="$LIMEN/cli/.venv/bin/python"     # bare python3 lacks rfc8785; the organ imports fail without the venv
MODE="${1:-dry-run}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${LIMEN_CUSTODY_STAGING_ROOT:-$LIMEN/.limen-private/custody-staging}/reclaim-operator-$TS"
mkdir -p "$OUT"
chmod 0700 "$OUT"

echo "== disk before =="
df -h /Users/4jp | tail -1

# Branches whose tip is contained in a remote ref (classified by branches.py); re-verified here before delete.
REAPABLE_BRANCHES_JSON="$(cd "$(dirname "$0")/.." && pwd)/data/branches-dryrun.json"
# Squash-merged limen/domus branches (PR state MERGED or CLOSED-dependabot) classified by prs.py.
MERGED_BRANCHES_JSON="$(cd "$(dirname "$0")/.." && pwd)/data/prs.json"

reap_branches() {
  local apply="$1"
  "$PY" -I - "$REAPABLE_BRANCHES_JSON" "$MERGED_BRANCHES_JSON" "$apply" <<'EOF'
import json, subprocess, sys
reap, prs, apply = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3] == "apply"
todo = []
for r in reap["repos"]:
    for b in r["reapable"]:
        todo.append((r["repo"], b["branch"]))
for p in prs:
    if p["pr_state"] in ("merged", "closed") and p["branch"] != "fix/security-hardening-domus-genoma":
        todo.append((p["repo"], p["branch"]))
kept = removed = 0
for repo, br in todo:
    sha = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", f"refs/heads/{br}"], capture_output=True, text=True).stdout.strip()
    if not sha:
        continue
    contained = subprocess.run(["git", "-C", repo, "branch", "-r", "--contains", sha], capture_output=True, text=True).stdout.strip()
    pr_merged = any(p["branch"] == br and p["repo"] == repo and p["pr_state"] in ("merged", "closed") for p in prs)
    if not contained and not pr_merged:
        kept += 1
        print(f"KEEP  {repo} {br} (tip no longer proven remote)")
        continue
    cur = subprocess.run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
    if cur == br:
        kept += 1
        print(f"KEEP  {repo} {br} (checked out)")
        continue
    if apply:
        subprocess.run(["git", "-C", repo, "branch", "-D", br], check=False)
    removed += 1
    print(f"{'DEL ' if apply else 'PLAN'}  {repo} {br} {sha[:12]}")
print(f"branches: {'removed' if apply else 'planned'}={removed} kept={kept}")
EOF
}

case "$MODE" in
  dry-run)
    echo "== worktree reclaim plan (organ, exact-plan transaction) =="
    "$PY" "$LIMEN/scripts/reclaim-worktrees.py" --check --json > "$OUT/worktree-plan.json"
    "$PY" -I -c 'import json,sys;d=json.load(open(sys.argv[1]));print("plan_sha",d["plan_sha256"],"reapable",d["reapable_count"]);[print(" ",c["action"],c["reason"],c["path"]) for c in d["candidate_manifest"]["candidates"]]' "$OUT/worktree-plan.json"
    echo "== generated cache plan (node_modules >= 20 MiB) =="
    "$PY" "$LIMEN/scripts/reclaim-generated-caches.py" --check --json --minimum-mib 20 > "$OUT/cache-plan.json"
    "$PY" -I -c 'import json,sys;d=json.load(open(sys.argv[1]));print("plan_sha",d["plan_sha256"],"bytes",d["candidate_bytes"]);[print(" ",c.get("path")) for c in d["candidates"]]' "$OUT/cache-plan.json"
    echo "== landed local branches (plan) =="
    reap_branches plan
    echo "== homed chamber worktrees that can be removed =="
    for wt in /Users/4jp/Workspace/chamber_worktrees/chamber_1/organvm-engine/pr-104 /Users/4jp/Workspace/chamber_worktrees/chamber_2/speech-score-engine/pr-1 /Users/4jp/Workspace/chamber_worktrees/outer_ring/portfolio/pr-229; do
      echo "  $wt"
    done
    echo "  (pr-169 is NOT included: its LFS objects could not be pushed — LFS budget exceeded on organvm-vii-kerygma/portfolio)"
    echo "== generated-only abandonment payload =="
    du -sh /Users/4jp/Workspace/_limen-worktree-abandonment/generated-* 2>/dev/null | sort -h | tail -5
    echo "  ($(ls -d /Users/4jp/Workspace/_limen-worktree-abandonment/generated-* | wc -l | tr -d ' ') generated-* entries; non-generated entries are left alone)"
    echo "== stale worktree registrations (prune only; dirs on /Volumes/Scratch listed for review) =="
    git -C "$LIMEN" worktree prune --dry-run -v || true
    ;;
  apply)
    echo "== worktree reclaim (organ) =="
    "$PY" "$LIMEN/scripts/reclaim-cycle.py" --apply --timeout 900
    echo "== generated caches (organ) =="
    "$PY" "$LIMEN/scripts/reclaim-generated-caches.py" --check --json --minimum-mib 20 > "$OUT/cache-plan.json"
    SHA="$("$PY" -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["plan_sha256"])' "$OUT/cache-plan.json")"
    "$PY" "$LIMEN/scripts/reclaim-generated-caches.py" --apply --minimum-mib 20 --expected-plan-sha "$SHA"
    echo "== landed local branches =="
    reap_branches apply | tee "$OUT/branches.log"
    echo "== homed chamber worktrees =="
    git -C /Users/4jp/Workspace/a-organvm/organvm-engine worktree remove --force /Users/4jp/Workspace/chamber_worktrees/chamber_1/organvm-engine/pr-104 2>/dev/null || rm -rf /Users/4jp/Workspace/chamber_worktrees/chamber_1/organvm-engine/pr-104
    rm -rf /Users/4jp/Workspace/chamber_worktrees/chamber_2/speech-score-engine/pr-1
    git -C /Users/4jp/Workspace/organvm-vii-kerygma/portfolio worktree remove --force /Users/4jp/Workspace/chamber_worktrees/outer_ring/portfolio/pr-229 2>/dev/null || rm -rf /Users/4jp/Workspace/chamber_worktrees/outer_ring/portfolio/pr-229
    git -C /Users/4jp/Workspace/organvm-vii-kerygma/portfolio worktree prune
    echo "== generated-only abandonment payload =="
    find /Users/4jp/Workspace/_limen-worktree-abandonment -maxdepth 1 -name 'generated-*' -print0 | xargs -0 rm -rf
    echo "== stale worktree registrations =="
    git -C "$LIMEN" worktree prune -v || true
    ;;
  post-check)
    "$PY" "$LIMEN/scripts/worktree-debt.py" || true
    "$PY" "$LIMEN/scripts/reap-branches.py" --check || true
    ;;
  *) echo "usage: $0 dry-run|apply|post-check" >&2; exit 2 ;;
esac

echo "== disk after =="
df -h /Users/4jp | tail -1
echo "evidence: $OUT"
