#!/usr/bin/env bash
# dustin-build-done — exit 0 ⟺ the dustin full-build state is COHERENT (default)
# or COMPLETE (--complete: every runway phase done in all three repos).
#
# Executable definition of done for docs/plans/2026-08-14-dustin-full-build.md
# (issue #2390). Binds plan decisions D1 (atomic per-phase completion pass),
# D2 (ladder mutations only at phase boundaries), D3 (CONS deliverable renderer
# at src/deliverable.js, never the roadmap engine's src/render.js), D4 (NAS-P05
# gated corpus-import leaf), D5 (phases complete as a contiguous prefix in
# ladder/version order per repo).
#
# COHERENT, per venture repo (post-dsp-platform, the-consulate,
# new-ancients-social):
#   - clone present and HEAD == origin/main (GitHub is the copy of record)
#   - done phases form a contiguous prefix in ladder order
#   - every done phase passes `bin/check-roadmap.js --phase-done <id>`; done
#     phases past v0.1.0 also need origin tag v<version> and a CLOSED "Pnn "
#     milestone (P01 predates the completion protocol — its milestone state is
#     historical)
#   - package.json version == the last done phase's version (validator check E)
#   - gated phases still carry status GATED (planned-never-started)
#   - the repo's validator and full test suite are green at HEAD
#   - a fresh capture reconciles to PARITY via the repo's own reconcile tool
# Prints one FRONTIER line per repo: the next buildable phase, or COMPLETE
# with the gated frontier named.
#
# Predicate exit codes are read bare, never through a pipe (CLAUDE.md).
set -u

MODE="${1:-}"
LIMEN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
note() { printf '%-4s %s\n' "$1" "$2"; if [ "$1" = FAIL ]; then FAIL=1; fi; }

TMPDIR_DONE="$(mktemp -d /tmp/dustin-build-done.XXXXXX)"
trap 'rm -rf "$TMPDIR_DONE"' EXIT

runway_for() {
  case "$1" in
    post-dsp-platform)   echo "DSP-P02 DSP-P03 DSP-P04 DSP-P05 DSP-P06 DSP-P07 DSP-P08" ;;
    the-consulate)       echo "CONS-P02 CONS-P03 CONS-P04 CONS-P05 CONS-P06" ;;
    new-ancients-social) echo "NAS-P02 NAS-P03 NAS-P04 NAS-P05 NAS-P06 NAS-P07" ;;
  esac
}
gated_for() {
  case "$1" in
    post-dsp-platform)   echo "DSP-P09 DSP-P10" ;;
    the-consulate)       echo "CONS-P07" ;;
    new-ancients-social) echo "NAS-P08 NAS-P09" ;;
  esac
}

check_repo() {
  local r="$1"
  local d="/Users/4jp/Workspace/$r"

  if [ ! -d "$d/.git" ]; then
    note FAIL "$r: no clone at $d (GitHub is the copy of record — reclone)"
    return
  fi

  local local_sha remote_sha
  local_sha="$(git -C "$d" rev-parse HEAD 2>/dev/null)"
  remote_sha="$(gh api "repos/4444J99/$r/commits/main" --jq .sha 2>/dev/null)"
  if [ -n "$remote_sha" ] && [ "$local_sha" = "$remote_sha" ]; then
    note OK "$r: clone in sync with origin/main ($local_sha)"
  else
    note FAIL "$r: local $local_sha != remote ${remote_sha:-<unreachable>}"
  fi

  # Phase rows in ladder order (check E guarantees version order): id|version|status
  local rows
  rows="$(node -e "
    const l = JSON.parse(require('fs').readFileSync('$d/roadmap/ladder.json','utf8'));
    for (const p of l.phases) console.log([p.id, p.version, p.status].join('|'));
  " 2>/dev/null)"
  if [ -z "$rows" ]; then
    note FAIL "$r: cannot read phases from roadmap/ladder.json"
    return
  fi

  local milestones="$TMPDIR_DONE/$r-milestones.txt"
  gh api --paginate "repos/4444J99/$r/milestones?state=all&per_page=100" \
    --jq '.[] | "\(.title)|\(.state)"' > "$milestones" 2>/dev/null

  local last_done_id="" last_done_ver="" frontier="" seen_nondone=0
  local pid pver pstatus pnum
  while IFS='|' read -r pid pver pstatus; do
    if [ "$pstatus" = done ]; then
      if [ "$seen_nondone" -eq 1 ]; then
        note FAIL "$r: $pid done AFTER a non-done phase — done prefix not contiguous (D5)"
      fi
      last_done_id="$pid"; last_done_ver="$pver"
      ( cd "$d" && node bin/check-roadmap.js --phase-done "$pid" >/dev/null 2>&1 )
      if [ $? -eq 0 ]; then
        note OK "$r: $pid --phase-done true"
      else
        note FAIL "$r: $pid marked done but --phase-done is false"
      fi
      if [ "$pver" != "0.1.0" ]; then
        gh api "repos/4444J99/$r/git/ref/tags/v$pver" >/dev/null 2>&1
        if [ $? -eq 0 ]; then
          note OK "$r: tag v$pver on remote"
        else
          note FAIL "$r: tag v$pver missing on remote"
        fi
        pnum="${pid##*-}"
        if grep "^$pnum " "$milestones" 2>/dev/null | grep -q '|closed$'; then
          note OK "$r: milestone $pnum closed"
        else
          note FAIL "$r: milestone $pnum not closed for done phase $pid"
        fi
      fi
    else
      if [ "$seen_nondone" -eq 0 ]; then frontier="$pid"; fi
      seen_nondone=1
    fi
  done <<< "$rows"

  local pkg_ver
  pkg_ver="$(node -e "console.log(JSON.parse(require('fs').readFileSync('$d/package.json','utf8')).version)" 2>/dev/null)"
  if [ -n "$last_done_ver" ] && [ "$pkg_ver" = "$last_done_ver" ]; then
    note OK "$r: package.json version $pkg_ver == last done phase ($last_done_id)"
  else
    note FAIL "$r: package.json version $pkg_ver != last done phase version ${last_done_ver:-<none>}"
  fi

  local g gstatus
  for g in $(gated_for "$r"); do
    gstatus="$(printf '%s\n' "$rows" | grep "^$g|" | cut -d'|' -f3)"
    if [ "$gstatus" = GATED ]; then
      note OK "$r: gated phase $g untouched"
    else
      note FAIL "$r: gated phase $g has status '${gstatus:-<missing>}' — expected GATED"
    fi
  done

  ( cd "$d" && node bin/check-roadmap.js >/dev/null 2>&1 )
  if [ $? -eq 0 ]; then note OK "$r: check-roadmap green"; else note FAIL "$r: check-roadmap red"; fi

  ( cd "$d" && npm test >/dev/null 2>&1 )
  if [ $? -eq 0 ]; then note OK "$r: tests green"; else note FAIL "$r: tests red"; fi

  local cap="$TMPDIR_DONE/$r-capture.json"
  gh issue list -R "4444J99/$r" --state all --limit 500 \
    --json number,title,state,body,labels,milestone,url > "$cap" 2>/dev/null
  ( cd "$d" && node bin/reconcile-issues.js --capture "$cap" >/dev/null 2>&1 )
  if [ $? -eq 0 ]; then note OK "$r: issue reconcile PARITY"; else note FAIL "$r: issue reconcile has defects"; fi

  local runway_frontier="" p pstat
  for p in $(runway_for "$r"); do
    pstat="$(printf '%s\n' "$rows" | grep "^$p|" | cut -d'|' -f3)"
    if [ "$pstat" != done ]; then runway_frontier="$p"; break; fi
  done
  if [ -n "$runway_frontier" ]; then
    echo "FRONTIER $r: $runway_frontier"
  else
    echo "FRONTIER $r: COMPLETE (gated frontier: $(gated_for "$r"))"
  fi

  if [ "$MODE" = "--complete" ]; then
    for p in $(runway_for "$r"); do
      pstat="$(printf '%s\n' "$rows" | grep "^$p|" | cut -d'|' -f3)"
      if [ "$pstat" = done ]; then
        note OK "$r: runway phase $p done"
      else
        note FAIL "$r: runway phase $p not done (status '${pstat:-<missing>}')"
      fi
    done
  fi
}

check_repo post-dsp-platform
check_repo the-consulate
check_repo new-ancients-social

# ── limen side ────────────────────────────────────────────────────────────────

python3 "$LIMEN_ROOT/scripts/session-plan.py" audit > "$TMPDIR_DONE/plan-audit.txt" 2>&1
if grep -E "GAP.*dustin-full-build" "$TMPDIR_DONE/plan-audit.txt" >/dev/null 2>&1; then
  note FAIL "limen: plan chain GAP for dustin-full-build"
else
  note OK "limen: plan chain has no GAP for dustin-full-build"
fi

if [ "$FAIL" -eq 0 ]; then
  if [ "$MODE" = "--complete" ]; then
    echo "DUSTIN FULL BUILD: COMPLETE — all runway phases done, state coherent"
  else
    echo "DUSTIN BUILD STATE: COHERENT — frontier above"
  fi
else
  echo "DUSTIN BUILD STATE: INCOHERENT — failures above"
fi
exit "$FAIL"
