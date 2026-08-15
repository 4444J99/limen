#!/usr/bin/env bash
# no-tasks-on-me.sh — executable predicate for the Closeout Definition.
#
# Proves the invariant the charter demands but never mechanized:
#   "A his-hand task never hangs on him, on Claude's head, or in recall-only
#    memory — every owed item lives in a git-tracked owner record, and no
#    preserved work is stranded on a local-only ref."
#
# Recall-only memory (~/.claude/.../memory) lives OUTSIDE the repo, so anything
# parked only there hangs on this machine, not in a durable home. This script
# is the permanent home for that guarantee: run it instead of re-auditing by
# hand each session.
#
# Exit 0  <=>  nothing hangs on me.  Idempotent: a re-run mutates nothing.
#
# PII firewall (memory: health-pii-in-generator-code) — the registry is
# git-tracked and PUBLISHES, so this script must NOT hardcode any of his
# specific conditions/drugs. It scans only for generic measurement/dose SHAPES
# (which name nothing of his) plus an OPTIONAL off-repo denylist; the specific
# literals, if ever enumerated, live off-repo and never enter git.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REGISTRY="${LIMEN_HIS_HAND_LEVERS:-$ROOT/his-hand-levers.json}"
DENYLIST="${LIMEN_PII_DENYLIST:-$HOME/Workspace/_health-private/pii-denylist.txt}"

fail=0
ok()  { printf 'ok    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=1; }

# ---------------------------------------------------------------------------
# 1-4: registry integrity, completeness, owner-traceability, and PII-safety.
# ---------------------------------------------------------------------------
if ! python3 - "$REGISTRY" "$DENYLIST" <<'PY'; then fail=1; fi
import json, re, sys
reg_path, deny_path = sys.argv[1], sys.argv[2]
rc = 0
try:
    d = json.load(open(reg_path))
except Exception as e:
    print(f"FAIL  registry not valid JSON: {e}"); sys.exit(1)
levers = d.get("levers") if isinstance(d, dict) else None
if not isinstance(levers, list) or not levers:
    print("FAIL  registry has no non-empty 'levers' list — the permanent home is missing/broken")
    sys.exit(1)

REQUIRED = ("id", "label", "owner", "cost", "unlocks", "source_task")
seen = set()
for lev in levers:
    lid = str(lev.get("id", "<no-id>"))
    for k in REQUIRED:
        if not str(lev.get(k, "")).strip():
            print(f"FAIL  lever {lid}: missing/empty required field '{k}' (un-ownable / un-traceable)"); rc = 1
    if lid in seen:
        print(f"FAIL  duplicate lever id: {lid}"); rc = 1
    seen.add(lid)

# PII firewall — generic, non-identifying shapes only (names nothing of his).
blob = json.dumps(d).lower()
SHAPES = r"\b\d+\s?mg\b|\bmg/dl\b|\bmmhg\b|\b\d+\s?mcg\b|\b\d+\s?ml\b|\bbpm\b"
shape_hits = sorted(set(re.findall(SHAPES, blob)))
if shape_hits:
    print(f"FAIL  registry contains clinical measurement/dose shapes {shape_hits} — health data leaked into a published file"); rc = 1

# Optional off-repo denylist of specific literals (kept off-repo so it never publishes).
import os
if os.path.exists(deny_path):
    terms = [t.strip().lower() for t in open(deny_path) if t.strip() and not t.startswith("#")]
    deny_hits = sorted({t for t in terms if t in blob})
    if deny_hits:
        print(f"FAIL  registry contains {len(deny_hits)} off-repo-denylisted literal(s) — PII leak"); rc = 1
    else:
        print(f"ok    registry clear of all {len(terms)} off-repo-denylisted literals")
else:
    print(f"note  off-repo PII denylist absent ({deny_path}) — specific-literal scan skipped; shape scan still enforced")

if rc == 0:
    print(f"ok    registry: {len(levers)} levers, all owned + traceable, no PII shapes")
sys.exit(rc)
PY

# ---------------------------------------------------------------------------
# 5: no preserved work stranded on a local-only ref.
#    Loss-proof preserve refs use the '*-staged-*' naming. Each must be either
#    merged (reachable from origin/main) or cited by name/sha in the registry —
#    otherwise the work lives only on this machine with no durable pointer.
#    (Enumerate all branch refs and grep-filter: a for-each-ref glob does NOT
#     cross the '/' in 'heal/...', so it would silently match nothing.)
# ---------------------------------------------------------------------------
staged_refs="$(git for-each-ref --format='%(refname:short)' refs/heads/ | grep -- '-staged-' || true)"
if [ -z "$staged_refs" ]; then
  ok "no '*-staged-*' preserve refs present (nothing to strand)"
else
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    sha="$(git rev-parse "$name")"; short="$(git rev-parse --short "$name")"
    if git merge-base --is-ancestor "$sha" origin/main 2>/dev/null; then
      ok "preserve ref $name merged into origin/main"
    # grep the file directly — a `printf | grep -q` pipeline under pipefail false-fails
    # via SIGPIPE (exit 141) once the registry outgrows the pipe buffer: grep -q exits
    # at first match and the still-writing printf poisons the pipeline's status.
    elif grep -qiE -- "$name|${short}|${sha:0:7}" "$REGISTRY"; then
      ok "preserve ref $name cited by a registry lever (durable pointer)"
    else
      bad "preserve ref $name ($short) is STRANDED — not on origin/main and not cited by any lever. Merge it, cite it in a lever's source_task, or delete it."
    fi
  done <<< "$staged_refs"
fi

# ---------------------------------------------------------------------------
# 6: the obligations surface can load + union the registry (it renders to the
#    money/obligations face — a registry it can't union is not a real home).
# ---------------------------------------------------------------------------
if ! python3 - "$REGISTRY" <<'PY'; then fail=1; fi
import json, sys
d = json.load(open(sys.argv[1]))
levs = d.get("levers", [])
ids = [l.get("id") for l in levs]
if len(ids) != len(set(ids)):
    print("FAIL  duplicate ids would collide in the obligations union"); sys.exit(1)
print(f"ok    obligations surface can union {len(levs)} levers without collision")
PY

# ---------------------------------------------------------------------------
# 7: every lever is OWNED IN THE GRAPH, not just in this file. A lever that
#    lives only in JSON still hangs on whoever reads the JSON. Durable
#    invariant (always enforced): each lever carries an `issue` number — a
#    needs-human issue is its individually-closeable home. Online deepening:
#    confirm no stamped pointer is dangling. A CLOSED issue means the lever was
#    pulled (not a failure). Keep in sync with: scripts/sync-hishand-issues.py --apply
# ---------------------------------------------------------------------------
if ! python3 - "$REGISTRY" <<'PY'; then fail=1; fi
import json, sys
d = json.load(open(sys.argv[1]))
rc = 0
for lev in d.get("levers", []):
    if not isinstance(lev.get("issue"), int):
        print(f"FAIL  lever {lev.get('id','<no-id>')}: no `issue` pointer — owned in the file "
              f"but not assigned in the graph. Run scripts/sync-hishand-issues.py --apply"); rc = 1
if rc == 0:
    print("ok    every lever carries a needs-human issue pointer (owned + assigned in the graph)")
sys.exit(rc)
PY

if command -v gh >/dev/null 2>&1 && [ -z "${LIMEN_OFFLINE:-}" ]; then
  slug="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null || true)"
  if [ -n "$slug" ]; then
    open_n=0; closed_n=0
    while IFS= read -r num; do
      [ -n "$num" ] || continue
      state="$(gh api "repos/$slug/issues/$num" --jq .state 2>/dev/null || true)"
      case "$state" in
        open)   open_n=$((open_n + 1)) ;;
        closed) closed_n=$((closed_n + 1)) ;;
        *)      bad "lever issue #$num is a DANGLING pointer (no such issue on $slug)" ;;
      esac
    done < <(python3 -c 'import json,sys;[print(l["issue"]) for l in json.load(open(sys.argv[1])).get("levers",[]) if isinstance(l.get("issue"),int)]' "$REGISTRY")
    ok "graph: $open_n levers owed (open), $closed_n pulled (closed), 0 dangling"
  fi
else
  printf 'note  %s\n' "offline — skipped GitHub open/closed check (pointer-presence still enforced)"
fi

# ---------------------------------------------------------------------------
# 8: no DANGLING PROSE lever reference. A lever id named in the registry's prose
#    (_doc/wall/spine, a label, a note, steps) but never DEFINED as an object here
#    is a pointer to nothing durable — the exact gap §7's issue-check cannot catch
#    (it validates objects, not references). Every `L-*` id the file mentions must
#    resolve to a lever object in THIS git-tracked registry; external-organ atoms
#    must be referenced descriptively, not by a bare id that reads as 'defined here.'
# ---------------------------------------------------------------------------
if ! python3 - "$REGISTRY" <<'PY'; then fail=1; fi
import json, re, sys
d = json.load(open(sys.argv[1]))
obj_ids = {l.get("id") for l in d.get("levers", [])}
referenced = set(re.findall(r"\bL-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", json.dumps(d)))
dangling = sorted(referenced - obj_ids)
if dangling:
    print(f"FAIL  registry prose names {len(dangling)} lever id(s) with no object here: {dangling} — "
          "define each as a lever object, or reference the external atom descriptively (not by bare id).")
    sys.exit(1)
print(f"ok    every lever id named in prose resolves to a defined object ({len(obj_ids)} levers)")
PY

# ---------------------------------------------------------------------------
# 9: no SPENT branch hangs. A local branch whose work is already landed on
#    origin/main (a real merge, or a MERGED PR with an un-advanced tip) is pure
#    residue: `git worktree remove` / `gh pr merge --delete-branch` leave the
#    LOCAL head ref behind, so squash-merged branches pile up as the "1 ahead /
#    N behind housekeeping" that used to get hand-waved each session. The
#    branch-reap organ (scripts/reap-branches.py) proves the fixed point — exit
#    0 <=> no provably-landed branch lingers PAST the digestion grace window
#    (LIMEN_BRANCH_REAP_GRACE_MIN; a branch spent seconds ago is the beat
#    mid-digestion, not hanging debt). Reaping is loss-free
#    (reflog-recoverable) so the organ self-heals it on the hygiene beat; here we
#    only ASSERT it, so a closeout cannot pass with spent branches hanging.
#    Fails safe offline (ancestor-only). Genuinely-unfinished branches live in
#    their OWN git-tracked home (docs/branch-hygiene.md), never here.
# ---------------------------------------------------------------------------
if ! python3 "$ROOT/scripts/reap-branches.py" --check; then
  bad "spent branches are lingering — see the [reap-branches] lines above: branches marked 'authorized' are already covered by the acceptance ledger (standing grant or per-branch event) and need only scripts/reap-branches.py --apply; only 'needs-acceptance' branches require a new docs/branch-reap-acceptance.jsonl event"
fi

# ---------------------------------------------------------------------------
# 10: no un-homed personal fact hangs on the session. The personal-facts
#     registry (institutio/governance/personal-facts.yaml) owns every durable
#     PII atom; scripts/identity.py verify is its predicate. Neither §1-9 nor
#     credential-wall.py covers unpopulated IDENTITY/PII — this is that arm. A
#     blank applicable&required atom (DOB/address/phone) is fine ONLY if it is
#     homed as a lever (L-IDENTITY-POPULATE) whose issue the operator owns; then
#     the relay cites the lever, never the atom. Green iff the atoms are present
#     OR the populate lever homes the gap — a closeout can no longer pass with a
#     personal fact silently un-homed (the phi.pdf chat-ask defect).
# ---------------------------------------------------------------------------
if ! python3 "$ROOT/scripts/identity.py" verify >/dev/null 2>&1; then
  if ! grep -q 'L-IDENTITY-POPULATE' "$ROOT/his-hand-levers.json" 2>/dev/null; then
    bad "personal-fact atoms are unpopulated and no L-IDENTITY-POPULATE lever homes the gap — add the lever to his-hand-levers.json (or populate the store); never leave it as a chat ask"
  fi
fi

# ---------------------------------------------------------------------------
# 11: the SESSION'S OWN worktree carries nothing. §1-10 prove the REGISTRY is
#     clean; not one of them reads working-tree state (no `git status`, no
#     `git worktree list`, no `ps`), so a closeout could pass with this
#     session's own branch dirty or unpushed. That is the single most common
#     premature-COMPLETE shape — measured across five agent lanes in the
#     2026-08-15 insights sweep, where the work landed and only the proof was
#     missing.
#
#     Scope is deliberately SELF, not the estate. cli/src/limen/worktree_debt.py
#     classifies whatever root you run FROM as `self/live-checkout` (debt=false),
#     so the aggregate report can never answer "is my own tree clean?" — it has
#     to be asked directly. Estate-wide debt is the reaper organ's
#     (scripts/worktree-debt.py on the heartbeat rung); folding its inherited
#     backlog into a session gate would red every closeout for work that is not
#     this session's — exactly the "red that is not yours" exception the
#     closeout skill already carves out. It is REPORTED here, never failed.
#
#     The LIVE checkout is permanently dirty BY DESIGN (capture.sh snapshots it
#     to a side ref) and tasks.yaml/tasks.yaml.lock are daemon-owned, so the
#     dirty arm skips the live root and honours capture.sh's RUNTIME_GLOBS.
#     A predicate that reds the live checkout is a failed predicate, not a
#     finding — it would be disabled inside a week.
# ---------------------------------------------------------------------------
branch="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '<detached>')"

if [ -f "$ROOT/.git" ]; then
  # `.git` is a FILE only in a linked worktree — this session's isolation root.
  self_dirty="$(git -C "$ROOT" status --porcelain | grep -vE '^.. (tasks\.yaml|tasks\.yaml\.lock)$' || true)"
  if [ -n "$self_dirty" ]; then
    n="$(printf '%s\n' "$self_dirty" | wc -l | tr -d ' ')"
    bad "this session's worktree ($branch) has $n uncommitted path(s) — commit them with an explicit \`git add <path>\` (never -A), or discard them. A closeout cannot pass over its own dirty tree."
  else
    ok "session worktree ($branch) is clean (daemon-owned runtime paths excluded)"
  fi
else
  ok "live checkout — dirty BY DESIGN (capture.sh side-ref); self-tree cleanliness is capture.sh's invariant, not this gate's"
fi

upstream="$(git -C "$ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
if [ -n "$upstream" ]; then
  ahead="$(git -C "$ROOT" rev-list --count "$upstream..HEAD" 2>/dev/null || echo 0)"
  if [ "$ahead" -gt 0 ]; then
    bad "this session's branch ($branch) is $ahead commit(s) ahead of $upstream — UNPUSHED. 'On disk' is not done: push it, then re-run."
  else
    ok "session branch ($branch) is fully pushed to $upstream"
  fi
else
  ahead="$(git -C "$ROOT" rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"
  if [ "$ahead" -gt 0 ]; then
    bad "this session's branch ($branch) carries $ahead commit(s) past origin/main and has NO UPSTREAM — the work exists only on this machine. Push it, then re-run."
  else
    ok "session branch ($branch) carries no unpushed work"
  fi
fi

# Estate-wide lifecycle debt: reported, never failed (the reaper organ owns it).
estate_debt="$(python3 "$ROOT/scripts/worktree-debt.py" --json 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("debt","?"))' 2>/dev/null || echo '?')"
printf 'note  %s\n' "estate worktree debt: $estate_debt (owner: scripts/worktree-debt.py on the heartbeat reaper rung — inherited fleet debt is not this session's closeout bar)"

# ---------------------------------------------------------------------------
# 12: no stray watcher outlives the session. scripts/orphan-watchers.py is
#     beat-wired and SessionEnd-wired, but a session that ends by DECLARING
#     closeout (rather than by the SessionEnd hook firing) never ran it — so
#     hand-rolled pollers could survive a "CLOSEOUT COMPLETE" indefinitely.
#     That is the 2026-07-15 endless-watcher incident's residue, and this is
#     the arm that closes it on the interactive path.
# ---------------------------------------------------------------------------
if ! python3 "$ROOT/scripts/orphan-watchers.py" --check; then
  bad "orphaned watcher process(es) survive this session — reap them (scripts/orphan-watchers.py --check --reap, armed by LIMEN_ORPHAN_WATCHER_REAP=1) before declaring closeout"
fi

# ---------------------------------------------------------------------------
# 13: a working session leaves a durable artifact. "Zero artifacts" was
#     explicitly corrected as a FAILURE, not a clean result — but the honest
#     mechanization is narrow: a genuinely read-only session owes nothing, and
#     a predicate cannot detect "did you learn something." What it CAN prove is
#     the degenerate shape: a branch that committed work touching ONLY logs/
#     and daemon-owned runtime paths has produced no durable artifact at all.
# ---------------------------------------------------------------------------
changed="$(git -C "$ROOT" diff --name-only origin/main...HEAD 2>/dev/null || true)"
if [ -z "$changed" ]; then
  ok "read-only session (HEAD at origin/main) — no durable artifact owed"
else
  durable="$(printf '%s\n' "$changed" | grep -vE '^(logs/|tasks\.yaml)' || true)"
  if [ -z "$durable" ]; then
    bad "this branch changed only logs/ and daemon-owned runtime paths — ZERO durable artifacts. Codify what this session learned into a tracked owner (a doc, a predicate, a registry entry) before closing out."
  else
    n="$(printf '%s\n' "$durable" | wc -l | tr -d ' ')"
    ok "session produced $n durable artifact path(s) beyond logs/ and runtime state"
  fi
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "VERDICT: tasks are hanging — see FAIL lines above. Hang each in its owner's git-tracked record, then re-run."
  exit 1
fi
echo "VERDICT: nothing hangs on me — every owed task lives in a git-tracked owner record."
