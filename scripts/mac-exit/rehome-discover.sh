#!/usr/bin/env bash
# READ-ONLY discovery of git worktrees on the external volumes whose .git pointer file names a path under /Users.
#
# WHY: erase the Mac and every such worktree is a dead directory. This lists them, with their parent repository, so
# scripts/mac-exit/rehome.sh can convert the live ones. Run it right before a rehome: the Mac is live and the list moves.
# Every scanned volume is reported; the volumes rehome.sh must never convert (for example the independent replica) are
# named to rehome.sh itself through REHOME_SKIP_VOLUMES, not here.
#
# Rows with admin_exists=no are already orphaned (the Mac-side metadata is gone); there is nothing to re-home for them.
#
# usage: scripts/mac-exit/rehome-discover.sh [OUT_DIR [VOLUME...]]
#   OUT_DIR   default: $TMPDIR/mac-exit-rehome-discovery
#   VOLUME    the name of a volume under /Volumes to scan (give as many as you need). With none given, every mount point
#             directly under /Volumes is scanned except the boot volume (realpath / or the same device as $HOME).
# writes OUT_DIR/discovery.tsv (volume, worktree, admin_dir, parent_repo, admin_id, admin_exists)

set -u
export GIT_OPTIONAL_LOCKS=0
out="${1:-${TMPDIR:-/tmp}/mac-exit-rehome-discovery}"
(( $# > 0 )) && shift
volumes=("$@")

dev_of() { stat -c %d "$1" 2>/dev/null || stat -f %d "$1" 2>/dev/null; }   # GNU first: BSD stat has no -c, GNU stat -f means something else

# mount points directly under /Volumes that are real mounts, minus the boot volume
discover_volumes() {
  local line mp real boot_dev re='^.+ on (/Volumes/[^/]+) \([^()]*\)$'
  boot_dev="$(dev_of "$HOME")"
  while IFS= read -r line; do
    [[ "$line" =~ $re ]] || continue
    mp="${BASH_REMATCH[1]}"
    real="$(cd -P "$mp" 2>/dev/null && pwd -P)" || continue
    [[ "$real" == / ]] && continue
    [[ -n "$boot_dev" && "$(dev_of "$mp")" == "$boot_dev" ]] && continue
    printf '%s\n' "${mp#/Volumes/}"
  done < <(mount)
}

if (( ${#volumes[@]} == 0 )); then
  while IFS= read -r v; do volumes+=("$v"); done < <(discover_volumes)
  echo "volumes (discovered): ${volumes[*]:-none}"
else
  echo "volumes (given): ${volumes[*]}"
fi

# a name is a single path component: anything else would scan outside /Volumes/<name>
for vol in ${volumes[@]+"${volumes[@]}"}; do
  [[ -n "$vol" && "$vol" != */* && "$vol" != . && "$vol" != .. ]] || { echo "BAD VOLUME NAME: $vol" >&2; exit 2; }
done

mkdir -p "$out"
tsv="$out/discovery.tsv"
printf 'volume\tworktree\tadmin_dir\tparent_repo\tadmin_id\tadmin_exists\n' > "$tsv"
: > "$out/discovery.find.err"
for vol in ${volumes[@]+"${volumes[@]}"}; do
  root="/Volumes/$vol"
  [[ -d "$root" ]] || { echo "NOT MOUNTED: $vol"; continue; }
  # bfs is the find on this host: no BSD -x (use -xdev), and keep stderr so a silent error cannot read as "none found"
  find "$root" -xdev -maxdepth 5 -type f -name .git -print0 2>> "$out/discovery.find.err" |
  while IFS= read -r -d '' g; do
    first=$(head -n 1 "$g" 2>/dev/null || true)
    [[ "$first" == "gitdir: /Users/"* ]] || continue
    adm="${first#gitdir: }"
    id=$(basename "$adm")
    if [[ -d "$adm" ]]; then
      exists=yes
      common=$(cd "$adm" && cd "$(cat commondir 2>/dev/null || echo ../..)" 2>/dev/null && pwd || echo "?")
      parent=$(dirname "$common")
    else
      exists=no; parent="?"
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$vol" "$(dirname "$g")" "$adm" "$parent" "$id" "$exists" >> "$tsv"
  done
done
echo "find stderr lines: $(wc -l < "$out/discovery.find.err" | tr -d ' ')"
echo "rows: $(( $(wc -l < "$tsv") - 1 ))"
awk -F'\t' 'NR>1 {c[$1 " admin_exists=" $6]++} END {for (k in c) print k, c[k]}' "$tsv" | sort
echo "discovery written: $tsv"
