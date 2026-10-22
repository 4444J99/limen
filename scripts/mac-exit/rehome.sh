#!/bin/bash
# Re-home git worktrees that live on an external volume so they no longer depend on the Mac's repositories.
#
# WHY: a linked worktree's .git file points at <repo>/.git/worktrees/<id> on the Mac. Erase the Mac and every such
# worktree is a dead directory. This builds a standalone store (a FILE-LEVEL copy of the parent repo's .git, which keeps
# unreachable objects, refs/stash and reflogs that a clone would drop) on an external and points each worktree at it.
#
#   REHOME_SKIP_VOLUMES=NAME[,NAME...] rehome.sh <discovery.tsv> <store-root> dry [out-dir]
#       read-only: print the plan and each worktree's BEFORE state
#   REHOME_SKIP_VOLUMES=NAME[,NAME...] rehome.sh <discovery.tsv> <store-root> apply [out-dir]
#       build stores, convert, verify, auto-rollback on any mismatch
#
# REHOME_SKIP_VOLUMES is REQUIRED: comma-separated volume names (the discovery.tsv "volume" column, no spaces around the
# commas) whose worktrees are never converted, for example the independent replica. Unset, both modes refuse (exit 64) and
# write nothing, so forgetting it can never convert the replica. Set but empty (REHOME_SKIP_VOLUMES=) converts every
# volume, deliberately. The dry run prints the list in force and the volume of every planned worktree: read it before apply.
#
# Mutations in apply mode, and nothing else: (1) NEW store directories under <store-root>; (2) the single file W/.git of
# each live worktree W on a volume that is not skipped (the old content is kept as <store>/worktrees/<id>/mac-link.orig, NOT
# inside W, because a file inside W shows up as untracked and makes the worktree look dirty). Nothing is deleted; the Mac
# repos are only read.
# Lessons from the fixture test: never set core.bare on the store (git status then fails in its worktrees); the
# independence check must skip mac-link.orig (it names the Mac path on purpose).
#
# discovery.tsv columns: volume, worktree, admin_dir, parent_repo, admin_id, admin_exists (header on line 1).
set -u
export GIT_OPTIONAL_LOCKS=0
disc="${1:?discovery.tsv}"; root="${2:?store root}"; mode="${3:-dry}"
out="${4:-${TMPDIR:-/tmp}/mac-exit-rehome-out}"
[[ "$mode" == dry || "$mode" == apply ]] || { echo "mode must be dry|apply" >&2; exit 2; }
[[ -f "$disc" ]] || { echo "no such discovery file: $disc" >&2; exit 2; }
# fail closed: an unset skip list must never mean "skip nothing" (unset and set-but-empty are different; test with +x)
[[ -n "${REHOME_SKIP_VOLUMES+x}" ]] || {
  echo "REHOME_SKIP_VOLUMES is not set: set REHOME_SKIP_VOLUMES to the comma-separated volume names whose worktrees must never be converted (the independent replica); set it empty (REHOME_SKIP_VOLUMES=) only to convert every volume" >&2
  exit 64
}
mkdir -p "$out"
results="$out/rehome-results.tsv"; rollback="$out/rollback.sh"
log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }

state() { # W -> head|ref|statushash
  local w="$1"
  printf '%s|%s|%s' "$(git -C "$w" rev-parse HEAD 2>/dev/null)" \
    "$(git -C "$w" symbolic-ref -q HEAD 2>/dev/null || echo detached)" \
    "$(git -C "$w" status --porcelain=v1 -z 2>/dev/null | shasum -a 256 | cut -d' ' -f1)"
}

# ENVIRON, not awk -v: -v would interpret backslash escapes in a volume name
skip="${REHOME_SKIP_VOLUMES:-}"; export REHOME_SKIP_VOLUMES="$skip"
candidates() {
  awk -F'\t' 'BEGIN { n = split(ENVIRON["REHOME_SKIP_VOLUMES"], a, ","); for (i = 1; i <= n; i++) if (a[i] != "") s[a[i]] = 1 }
              NR>1 && !($1 in s) && $6=="yes"' "$disc"
}
parents()    { candidates | awk -F'\t' '{print $4}' | sort -u; }

if [[ "$mode" == dry ]]; then
  log "DRY RUN -- nothing is written (store root: $root)"
  log "REHOME_SKIP_VOLUMES: ${skip:-<empty: EVERY volume is converted>}"
  avail_kb=$(df -k "$(dirname "$root")" 2>/dev/null | awk 'NR==2{print $4}')
  need=0
  while IFS= read -r p; do
    kb=$(du -sk "$p/.git" 2>/dev/null | awk '{print $1}'); need=$((need + ${kb:-0}))
    alt="no"; [[ -e "$p/.git/objects/info/alternates" ]] && alt="YES (would be skipped)"
    s="$root/$(basename "$p").git"; ex="new"; [[ -e "$s" ]] && ex="EXISTS (would be skipped)"
    printf 'PARENT %s  .git=%s KiB  alternates=%s  store=%s [%s]\n' "$p" "${kb:-?}" "$alt" "$s" "$ex"
  done < <(parents)
  n=0
  while IFS=$'\t' read -r vol w adm p id ex; do
    n=$((n + 1))
    printf 'WORKTREE %s  volume=%s parent=%s id=%s  before=%s\n' "$w" "$vol" "$(basename "$p")" "$id" "$(state "$w")"
  done < <(candidates)
  log "would convert $n worktree(s); stores need about ${need} KiB (x1), free ${avail_kb:-?} KiB"
  exit 0
fi

# ---- apply ----
log "REHOME_SKIP_VOLUMES: ${skip:-<empty: EVERY volume is converted>}"
mkdir -p "$root" || exit 2
avail_kb=$(df -k "$root" 2>/dev/null | awk 'NR==2{print $4}')   # after mkdir: df fails on a path that does not exist yet
want=$(candidates | wc -l | tr -d ' ')
printf 'worktree\tparent\tid\tbefore\tafter\tstate\n' > "$results"
printf '#!/bin/bash\n# Restores each converted worktree pointer. Valid only while the Mac repos still exist. Deletes nothing.\nset -eu\n' > "$rollback"
chmod +x "$rollback"
converted=0; failed=0

build_store() { # parent store
  local p="$1" s="$2"
  [[ -d "$p/.git" ]]                         || { log "SKIP $p: no .git directory"; return 1; }
  [[ -e "$p/.git/objects/info/alternates" ]] && { log "SKIP $p: uses alternates (would reference Mac paths)"; return 1; }
  [[ -e "$s" ]]                              && { log "SKIP $p: store already exists: $s"; return 1; }
  mkdir -p "$s"
  rsync -a --exclude 'pack/tmp_pack_*' --exclude 'tmp_obj_*' "$p/.git/objects/" "$s/objects/" || return 1
  rsync -a --exclude objects/ --exclude worktrees/ --exclude hooks/ --exclude '*.lock' "$p/.git/" "$s/"   || return 1
  rsync -a --exclude 'pack/tmp_pack_*' --exclude 'tmp_obj_*' "$p/.git/objects/" "$s/objects/" || return 1
  # a remote URL may embed a credential: strip userinfo from the COPY's config only
  sed -E 's#(://)[^/@ ]+@#\1#g' "$s/config" > "$s/config.redacted" && mv "$s/config.redacted" "$s/config" || return 1
  git --git-dir="$s" fsck --connectivity-only >/dev/null 2>&1 || { log "FSCK FAILED on $s"; return 1; }
}

convert_one() { # W parent store id
  local w="$1" p="$2" s="$3" id="$4" adm before after bad=""
  adm="$p/.git/worktrees/$id"
  before="$(state "$w")"
  [[ "$(sed -n '1s/^gitdir: //p' "$w/.git")" == "$adm" ]] || { printf '%s\t%s\t%s\t%s\t-\tskipped:pointer-changed\n' "$w" "$(basename "$p")" "$id" "$before" >> "$results"; return 1; }
  git --git-dir="$s" cat-file -e "${before%%|*}^{commit}" 2>/dev/null || { printf '%s\t%s\t%s\t%s\t-\tskipped:head-missing-in-store\n' "$w" "$(basename "$p")" "$id" "$before" >> "$results"; return 1; }
  [[ -e "$s/worktrees/$id/mac-link.orig" ]] && { printf '%s\t%s\t%s\t%s\t-\tskipped:backup-exists\n' "$w" "$(basename "$p")" "$id" "$before" >> "$results"; return 1; }
  mkdir -p "$s/worktrees/$id"
  rsync -a --exclude gitdir --exclude commondir --exclude locked "$adm/" "$s/worktrees/$id/" || return 1
  printf '../..\n' > "$s/worktrees/$id/commondir"
  printf '%s\n' "$w/.git" > "$s/worktrees/$id/gitdir"
  cp -p "$w/.git" "$s/worktrees/$id/mac-link.orig"
  printf 'gitdir: %s\n' "$s/worktrees/$id" > "$w/.git"
  after="$(state "$w")"
  [[ "$after" == "$before" ]]                                            || bad="$bad state-changed"
  git -C "$w" fsck --connectivity-only >/dev/null 2>&1                   || bad="$bad fsck"
  case "$(git -C "$w" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" in "$s"*) ;; *) bad="$bad common-dir";; esac
  # independence = no pointer file still names THE PARENT REPO's path (a generic /Users/ test would misfire whenever a
  # store happens to live under /Users, as it does in the self-test fixture)
  grep -qIF "$p" "$w/.git" "$s/worktrees/$id/gitdir" "$s/worktrees/$id/commondir" "$s/worktrees/$id/HEAD" 2>/dev/null && bad="$bad mac-path-left"
  if [[ -n "$bad" ]]; then
    cp -p "$s/worktrees/$id/mac-link.orig" "$w/.git"
    printf '%s\t%s\t%s\t%s\t%s\trolled-back:%s\n' "$w" "$(basename "$p")" "$id" "$before" "$after" "$bad" >> "$results"
    log "ROLLED BACK $w ($bad)"; return 1
  fi
  printf '%s\t%s\t%s\t%s\t%s\tconverted\n' "$w" "$(basename "$p")" "$id" "$before" "$after" >> "$results"
  printf "cp -p '%s' '%s'\n" "$s/worktrees/$id/mac-link.orig" "$w/.git" >> "$rollback"
  log "converted $w"
}

while IFS= read -r p; do
  s="$root/$(basename "$p").git"
  kb=$(du -sk "$p/.git" 2>/dev/null | awk '{print $1}')
  if (( ${kb:-0} > 25 * 1024 * 1024 )); then log "SKIP $p: .git over 25 GiB"; failed=$((failed + 1)); continue; fi
  if (( ${kb:-0} * 2 > ${avail_kb:-0} )); then log "SKIP $p: not enough free space"; failed=$((failed + 1)); continue; fi
  log "building store for $p -> $s"
  if ! build_store "$p" "$s"; then failed=$((failed + 1)); continue; fi
  while IFS=$'\t' read -r vol w adm pp id ex; do
    [[ "$pp" == "$p" ]] || continue
    if convert_one "$w" "$p" "$s" "$id"; then converted=$((converted + 1)); else failed=$((failed + 1)); fi
  done < <(candidates)
done < <(parents)

log "converted=$converted of $want candidates; failed_or_skipped=$failed; results: $results; rollback script: $rollback (not run)"
# PASS means every candidate was converted and verified. Zero work on a non-empty candidate list is NOT a pass.
(( failed == 0 && converted == want && want > 0 )) && { echo "RESULT: PASS"; exit 0; }
echo "RESULT: PARTIAL"; exit 1
