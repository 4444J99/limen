#!/usr/bin/env bash
# verify-hot-cache.sh — THE DISPOSABILITY PREDICATE: exit 0 ⟺ this machine is a hot flash cache.
#
# The Meeseeks law (plan 2026-07-30): every summoned surface is born for one purpose, executes,
# returns its result to source, and self-erases — residue is a defect. This predicate is the law's
# court: it proves the LOCAL machine holds nothing that is not re-summonable from upstream, so
# losing the disk (or jacking into a fresh one via portvs) loses zero state.
#
# Rungs (independent; every red is listed, then exit 1):
#   R1 spine     — chezmoi source is the real cartridge clone (scripts/cartridge-connected.py)
#   R2 capture   — deployed config carries no un-captured local state (scripts/chezmoi-drift.py)
#   R3 creds     — every materialized credential still authenticates (creds-hydrate --verify)
#   R4 toolchain — the declared toolchain is summonable (mise.toml resolves via `mise current`)
#   R5 repos     — every clone under $LIMEN_WORKDIR is clean, pushed, and stash-free
#   R6 residue   — the residue R5 steps over is within its declared caps (scripts/residue-census.py)
#
# R5 and R6 divide the same territory deliberately. R5 asks whether state is UN-SUMMONABLE (dirty,
# unpushed, stashed) and excludes worktrees/quarantines because they carry their own reap organs.
# R6 asks whether those organs are KEEPING UP — 39 worktrees, 517 branches, 10 GiB of runtime and a
# 571 MiB ledger are all perfectly summonable and still residue. Neither rung reaps anything.
#
# Fail-open where an ORGAN is absent (mise not installed → named advisory skip); loud where STATE
# is un-summonable (dirty tree, unpushed commits, credential drift). Read-only — never mutates.
# Beat-wired as the hot-cache sensor (sensors.yaml, gate LIMEN_HOTCACHE_CHECK, daily cadence).
set -uo pipefail
ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
WS="${LIMEN_WORKDIR:-$HOME/Workspace}"
cd "$ROOT"

red=0
fail() { echo "  ✗ $*"; red=1; }
ok()   { echo "  ✓ $*"; }
skip() { echo "  · $*"; }

echo "verify-hot-cache: exit 0 ⟺ this machine is disposable"

# R1 — the chezmoi spine points at the real cartridge clone.
if python3 scripts/cartridge-connected.py >/dev/null 2>&1; then
  ok "R1 spine — chezmoi source is the cartridge"
else
  fail "R1 spine — cartridge disconnected (scripts/cartridge-connected.py)"
fi

# R2 — no un-captured local config. Known standing debt: organvm/domus-genoma#359 (the
# pre-migration orphan snapshot) — this rung stays honestly red until that reconcile lands.
if python3 scripts/chezmoi-drift.py >/dev/null 2>&1; then
  ok "R2 capture — no un-captured local config"
else
  fail "R2 capture — local config drift (scripts/chezmoi-drift.py; reconcile owner: organvm/domus-genoma#359)"
fi

# R3 — validity, not presence: a machine whose creds are dead is not re-summonable elsewhere.
if python3 scripts/creds-hydrate.py --verify >/dev/null 2>&1; then
  ok "R3 creds — every materialized credential authenticates"
else
  fail "R3 creds — dead credential(s) (scripts/creds-hydrate.py --verify)"
fi

# R4 — the declared toolchain (mise.toml ranges) resolves. Organ-absent = advisory skip: the
# jack-in installs mise; its absence on a working floor is a gap, not un-summonable state.
if command -v mise >/dev/null 2>&1; then
  if mise current >/dev/null 2>&1; then
    ok "R4 toolchain — declared toolchain resolves (mise current)"
  else
    fail "R4 toolchain — declared toolchain unresolved (run: mise install)"
  fi
else
  skip "R4 toolchain — mise not installed (advisory; the jack-in installs it)"
fi

# R5 — every clone under $WS (depth ≤3) is clean, pushed, and stash-free. Session worktrees and
# quarantines are summoning residue with their OWN reclaim organs — excluded by marker, named here
# so the exclusion is visible, never silent.
R5_EXCLUDE='/\.claude/worktrees/|/\.limen-worktrees/|/\.worktrees/|_limen-orphan-quarantine|/\.domus-genoma-stub-'
r5_bad=0 r5_seen=0
while IFS= read -r gitdir; do
  d="${gitdir%/.git}"
  r5_seen=$((r5_seen + 1))
  probs=""
  [ -n "$(git -C "$d" status --porcelain 2>/dev/null | head -1)" ] && probs="dirty"
  if [ -n "$(git -C "$d" log --branches --not --remotes --oneline 2>/dev/null | head -1)" ]; then
    probs="${probs:+$probs, }unpushed"
  fi
  [ -n "$(git -C "$d" stash list 2>/dev/null | head -1)" ] && probs="${probs:+$probs, }stash"
  if [ -n "$probs" ]; then
    fail "R5 repos — ${d#"$WS"/}: $probs"
    r5_bad=$((r5_bad + 1))
  fi
done < <(find "$WS" -maxdepth 3 -name .git \( -type d -o -type f \) 2>/dev/null | grep -Ev "$R5_EXCLUDE" | sort)
if [ "$r5_bad" -eq 0 ]; then
  ok "R5 repos — $r5_seen clone(s) clean, pushed, stash-free (worktree/quarantine roots excluded by marker)"
fi

# R6 — the residue R5 deliberately steps over. R5 excludes worktrees and quarantines because they
# have their OWN reap organs; that exclusion is correct and stays. What was missing is anyone
# asking whether those organs KEEP UP. The census counts each residue class against its declared
# cap and names the organ or lever that relieves it — read-only, deletes nothing. Absent or
# unrunnable => advisory skip: a missing census is a gap in the court, not un-summonable state.
if [ -x "$ROOT/scripts/residue-census.py" ] || [ -f "$ROOT/scripts/residue-census.py" ]; then
  if r6_out="$(python3 "$ROOT/scripts/residue-census.py" --check 2>&1)"; then
    ok "R6 residue — every declared cap holds (nothing sprawling)"
  else
    while IFS= read -r line; do
      case "$line" in
        *BREACH*) fail "R6 residue —${line#*BREACH}" ;;
      esac
    done <<<"$r6_out"
  fi
else
  skip "R6 residue — scripts/residue-census.py absent (advisory)"
fi

if [ "$red" -eq 0 ]; then
  echo "HOT-CACHE: DISPOSABLE — every byte re-summonable from upstream"
  exit 0
fi
echo "HOT-CACHE: NOT DISPOSABLE — un-summonable state above (each red names its owner/fix)"
exit 1
