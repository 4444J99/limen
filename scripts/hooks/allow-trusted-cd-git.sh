#!/usr/bin/env bash
# PreToolUse hook: auto-approve safe Bash commands inside user-owned trees.
#
# WHY: Claude Code v2.1.x prompts on EVERY compound `cd <dir> && <cmd>` (the
# "bare-repo / untrusted git hooks" guard, upstream #32985). No settings
# allow-rule suppresses it — not even Bash(*) — and worktree/fleet sessions run
# under `--permission-mode auto` (which overrides settings.defaultMode:
# bypassPermissions), so the guard is live and floods every job with "approve
# Bash" prompts. The autonomous fleet runs thousands of
# `cd <repo> && (git|python|pytest|node|npm|osascript) ...` per day.
#
# TRUST BOUNDARY = THE DIRECTORY, WITH A TAIL GUARD. If the cd target resolves
# inside a tree the user owns (~/Workspace, ~/Code, ~/.claude, a .claude
# worktree, ~/.claude/jobs, /tmp) OR is an in-tree relative path (the fleet only
# ever runs from an already-trusted cwd), normal read/build/test/git chains are
# auto-approved. Hard-destructive tails still fall through to Claude's normal
# guard, even in trusted directories. Any cd target OUTSIDE those trees — an
# absolute foreign dir, a `..` escape, or an unresolved variable we can't place
# — also falls through untouched.
#
# DESTRUCTIVE COMMANDS ARE PATH-GATED, NOT BLANKET-PROMPTED (2026-07-09).
# The operator's standing spec (docs/never-hang-permission-spec.md): only
# DESTRUCTION of non-disposable things needs approval; deleting session
# artifacts must never prompt. So `rm`/`rmdir`/`git worktree remove`/
# `git branch -D`/`git reset --hard`/`git clean` route through a path analyzer:
# auto-approved only when EVERY affected path is disposable (a worktree under
# .claude/worktrees, ~/.claude/jobs, /tmp, $TMPDIR) or strictly inside a repo
# under ~/Workspace|~/Code (never a repo root itself, never `~`, never `/`).
# `reset --hard`/`clean` are disposable-roots-only (a fleet reset once wiped the
# live checkout). Hard-danger forms (sudo, force-push, shred, dd, mkfs,
# curl|sh, xargs rm, find -delete) are NEVER auto-approved here. A standalone
# command (no leading cd) gets the same analysis, plus a small read-only
# diagnostics allowlist (ps, route -n get, diskutil list/info, tmutil
# read-verbs, gh repo view/list/clone) measured from real prompt fossils.
# The user-level settings `ask` rules stay in place as the fail-safe backstop:
# if this hook stays silent, behavior degrades to a prompt, never to a silent
# approval.
#
# History:
#  - originally only handled the `git` case (cd\ *git*).
#  - 2026-06-24 generalized to the documented directory-trust design (absolute
#    trusted roots only).
#  - 2026-07-01 closed the fall-through prompts measured across fleet
#    transcripts: added ~/Code and ~/.claude to the trusted roots (the real
#    speech-score-engine lives at ~/Code and was 23/27 of all misses), taught it
#    to resolve $HOME / $CLAUDE_JOB_DIR / $CLAUDE_PROJECT_DIR targets instead of
#    matching them literally, trusted bare home (`cd ~`), and trusted in-tree
#    relative targets (`cd cli`, `cd web/app`) that carry no `..` escape and no
#    unresolved variable.
#  - 2026-07-09 path-aware destructive analyzer (worktree reaps stop
#    prompting); standalone-command branch; closed the cd-chain force-push /
#    shred hole (the old tail regex never matched them, silently defeating the
#    settings ask rules); multi-line tails with destructive verbs now fall
#    through instead of riding the first line's approval.
set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty')"

[ -n "$cmd" ] || exit 0

PHYS_HOME="$(cd -P "$HOME" 2>/dev/null && pwd -P || printf '%s' "$HOME")"
PHYS_TMPDIR=""
if [ -n "${TMPDIR:-}" ] && [ -d "$TMPDIR" ]; then
  case "$TMPDIR" in
    /var/folders/*|/private/var/folders/*|/tmp|/tmp/*)
      PHYS_TMPDIR="$(cd -P "$TMPDIR" 2>/dev/null && pwd -P || true)" ;;
  esac
fi

emit_allow() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"%s"}}\n' "$1"
  exit 0
}

# ── Danger classes ───────────────────────────────────────────────────────────
# HARD: never auto-approved by this hook, anywhere in the command text.
HARD_RE='(^|[;&|[:space:]])sudo([[:space:]]|$)|(^|[;&|[:space:]])dd[[:space:]][^;&|]*of=|(^|[;&|[:space:]])mkfs|(^|[;&|[:space:]])shred([[:space:]]|$)|chmod[[:space:]]+-[a-zA-Z]*R|chown[[:space:]]+-[a-zA-Z]*R|(curl|wget)[^;&]*[|][[:space:]]*(sh|bash|zsh)|git[[:space:]]+push[^;&|]*([[:space:]](--force|--force-with-lease[^[:space:]]*|-f|--delete|-d)([[:space:]]|$)|[[:space:]]\+[^[:space:]]+|[[:space:]]:[^[:space:]]+)|xargs[^;&|]*[[:space:]](rm|rmdir|shred)([[:space:]]|$)|find[[:space:]][^;&|]*-delete|(^|[;&|[:space:]])(sh|bash|zsh)[[:space:]]+-c[^;&]*[[:space:]](rm|rmdir|shred)[[:space:]]|(^|[;&|[:space:]])eval[[:space:]][^;&]*[[:space:]](rm|rmdir|shred)[[:space:]]'
# SOFT: destructive verbs the path analyzer may approve when every path is safe.
SOFT_RE='(^|[;&|[:space:]])(rm|rmdir)([[:space:]]|$)|git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)*(worktree[[:space:]]+remove|branch[[:space:]]|reset[[:space:]]|clean([[:space:]]|$))'

if printf '%s\n' "$cmd" | grep -Eiq "$HARD_RE"; then
  exit 0
fi

# ── Path trust helpers ───────────────────────────────────────────────────────

under_home() {  # is $1 a descendant of $HOME or $PHYS_HOME (or one of them itself)?
  # PORTABILITY: on Linux CI (and any config where $HOME sits under /tmp, e.g.
  # a mktemp-d hermetic test), a path inside the home tree must be governed
  # ONLY by the strict HOME-tree rules below — never by the generic /tmp
  # fallback (which would wrongly treat the whole primary checkout as
  # disposable/trusted). $TMPDIR is a SIBLING of $HOME, so it is unaffected.
  local p="$1"
  case "$p" in
    "$HOME"|"$HOME/"*) return 0 ;;
  esac
  if [ "$PHYS_HOME" != "$HOME" ]; then
    case "$p" in
      "$PHYS_HOME"|"$PHYS_HOME/"*) return 0 ;;
    esac
  fi
  return 1
}

expand_prefix() {  # expand a leading ~ / $HOME / $TMPDIR / $CLAUDE_* in $1; echo result ("" = refuse)
  local p="$1"
  case "$p" in
    "~") p="$HOME" ;;
    "~/"*) p="${HOME}${p#\~}" ;;
    '$HOME'*) p="${HOME}${p#\$HOME}" ;;
    '${HOME}'*) p="${HOME}${p#\$\{HOME\}}" ;;
    '$TMPDIR'*|'${TMPDIR}'*)
      [ -n "${TMPDIR:-}" ] || { printf ''; return 0; }
      case "$TMPDIR" in /var/folders/*|/private/var/folders/*|/tmp|/tmp/*) : ;; *) printf ''; return 0 ;; esac
      case "$p" in '$TMPDIR'*) p="${TMPDIR%/}${p#\$TMPDIR}" ;; *) p="${TMPDIR%/}${p#\$\{TMPDIR\}}" ;; esac ;;
    '$CLAUDE_JOB_DIR'*|'${CLAUDE_JOB_DIR}'*)
      [ -n "${CLAUDE_JOB_DIR:-}" ] || { printf ''; return 0; }
      case "$p" in '$CLAUDE_JOB_DIR'*) p="${CLAUDE_JOB_DIR%/}${p#\$CLAUDE_JOB_DIR}" ;; *) p="${CLAUDE_JOB_DIR%/}${p#\$\{CLAUDE_JOB_DIR\}}" ;; esac ;;
    '$CLAUDE_PROJECT_DIR'*|'${CLAUDE_PROJECT_DIR}'*)
      [ -n "${CLAUDE_PROJECT_DIR:-}" ] || { printf ''; return 0; }
      case "$p" in '$CLAUDE_PROJECT_DIR'*) p="${CLAUDE_PROJECT_DIR%/}${p#\$CLAUDE_PROJECT_DIR}" ;; *) p="${CLAUDE_PROJECT_DIR%/}${p#\$\{CLAUDE_PROJECT_DIR\}}" ;; esac ;;
  esac
  printf '%s' "$p"
}

trusted_dir() {  # is $1 (a directory path) inside a user-owned tree?
  local p
  p="$(expand_prefix "$1")"
  [ -n "$p" ] || return 1
  case "$p" in *'$'*) return 1 ;; esac
  case "/$p/" in */../*) return 1 ;; esac
  case "$p" in
    "$HOME"|"$HOME/Workspace"|"$HOME/Workspace/"*|"$HOME/Code"|"$HOME/Code/"*|"$HOME/.claude"|"$HOME/.claude/"*) return 0 ;;
    *.claude/worktrees/*) return 0 ;;
  esac
  if [ "$PHYS_HOME" != "$HOME" ]; then
    case "$p" in
      "$PHYS_HOME"|"$PHYS_HOME/Workspace"|"$PHYS_HOME/Workspace/"*|"$PHYS_HOME/Code"|"$PHYS_HOME/Code/"*|"$PHYS_HOME/.claude"|"$PHYS_HOME/.claude/"*) return 0 ;;
    esac
  fi
  # Generic /tmp trust — NEVER for a path inside the home tree (portability:
  # when $HOME itself sits under /tmp, home paths are governed only by the
  # strict clauses above).
  under_home "$p" && return 1
  case "$p" in
    /tmp|/tmp/*|/private/tmp|/private/tmp/*) return 0 ;;
  esac
  return 1
}

is_disposable() {  # proper descendant of a disposable container (lexical)
  local p="$1" td
  case "$p" in
    "$HOME/.claude/worktrees/"?*|"$HOME/.claude/jobs/"?*) return 0 ;;
    "$PHYS_HOME/.claude/worktrees/"?*|"$PHYS_HOME/.claude/jobs/"?*) return 0 ;;
    */.claude/worktrees/?*) return 0 ;;
  esac
  # $TMPDIR (a sibling of $HOME) stays disposable even when $HOME is under /tmp.
  if [ -n "${TMPDIR:-}" ]; then
    case "$TMPDIR" in
      /var/folders/*|/private/var/folders/*|/tmp|/tmp/*)
        td="${TMPDIR%/}"
        case "$p" in "$td"/?*) return 0 ;; esac ;;
    esac
  fi
  # Generic /tmp disposability — NEVER for a path inside the home tree.
  under_home "$p" && return 1
  case "$p" in
    /tmp/?*|/private/tmp/?*) return 0 ;;
  esac
  return 1
}

disposable_container_or_within() {  # a disposable container itself, or a proper descendant
  local p="$1" td
  case "$p" in
    "$HOME/.claude/worktrees"|"$HOME/.claude/jobs"|"$PHYS_HOME/.claude/worktrees"|"$PHYS_HOME/.claude/jobs") return 0 ;;
    */.claude/worktrees) return 0 ;;
  esac
  # Bare /tmp|/private/tmp container — NEVER when it is (part of) the home tree.
  if ! under_home "$p"; then
    case "$p" in /tmp|/private/tmp) return 0 ;; esac
  fi
  if [ -n "${TMPDIR:-}" ]; then
    td="${TMPDIR%/}"
    if [ "$p" = "$td" ]; then
      case "$td" in /var/folders/*|/private/var/folders/*|/tmp|/tmp/*) return 0 ;; esac
    fi
  fi
  is_disposable "$p"
}

phys_ok() {  # deepest EXISTING ancestor of $1 must physically resolve into a trusted class
  local d="$1" phys
  while [ ! -d "$d" ] && [ "$d" != "/" ] && [ -n "$d" ]; do
    d="${d%/*}"
    [ -n "$d" ] || d="/"
  done
  phys="$(cd -P "$d" 2>/dev/null && pwd -P)" || return 1
  case "$phys" in
    "$HOME/.claude"|"$HOME/.claude/"*|"$HOME/Workspace"|"$HOME/Workspace/"*|"$HOME/Code"|"$HOME/Code/"*) return 0 ;;
    "$PHYS_HOME/.claude"|"$PHYS_HOME/.claude/"*|"$PHYS_HOME/Workspace"|"$PHYS_HOME/Workspace/"*|"$PHYS_HOME/Code"|"$PHYS_HOME/Code/"*) return 0 ;;
  esac
  if [ -n "$PHYS_TMPDIR" ]; then
    case "$phys" in "$PHYS_TMPDIR"|"$PHYS_TMPDIR"/*) return 0 ;; esac
  fi
  # Generic /tmp physical trust — NEVER for a resolved path inside the home tree.
  under_home "$phys" && return 1
  case "$phys" in
    /tmp|/tmp/*|/private/tmp|/private/tmp/*) return 0 ;;
  esac
  return 1
}

in_repo_ok() {  # strictly INSIDE a repo under ~/Workspace|~/Code — never a repo root itself
  local p="$1" wsroot="" r d
  for r in "$HOME/Workspace" "$HOME/Code" "$PHYS_HOME/Workspace" "$PHYS_HOME/Code"; do
    case "$p" in "$r"/?*) wsroot="$r"; break ;; esac
  done
  [ -n "$wsroot" ] || return 1
  case "/$p/" in */.git/*) return 1 ;; esac
  if [ -e "$p/.git" ]; then return 1; fi
  d="${p%/*}"
  while [ -n "$d" ] && [ "$d" != "$wsroot" ]; do
    if [ -e "$d/.git" ]; then return 0; fi
    d="${d%/*}"
  done
  return 1
}

dest_path_ok() {  # may this path be destroyed without a prompt?  $1=token $2=ctx dir
  local p="$1" ctx="$2" trail=0 prefix dir
  [ -n "$p" ] || return 1
  p="$(expand_prefix "$p")"
  [ -n "$p" ] || return 1
  case "$p" in *'$'*) return 1 ;; esac
  case "$p" in */) trail=1 ;; esac
  case "$p" in
    /*) : ;;
    *) [ -n "$ctx" ] || return 1; p="${ctx%/}/$p" ;;
  esac
  case "/$p/" in */../*) return 1 ;; esac
  p="$(printf '%s' "$p" | sed -E 's#/+#/#g; s#/(\./)+#/#g; s#/\.$##; s#(.)/+$#\1#')"
  [ "$p" = "/" ] && return 1
  [ "$p" = "$HOME" ] && return 1
  [ "$p" = "$PHYS_HOME" ] && return 1
  case "$p" in
    *[\*\?\[]*)
      # Glob: judge the fixed directory prefix; only disposable containers may host globs.
      prefix="${p%%[\*\?\[]*}"
      case "$prefix" in */*) dir="${prefix%/*}" ;; *) return 1 ;; esac
      [ -n "$dir" ] || return 1
      disposable_container_or_within "$dir" || return 1
      phys_ok "$dir" || return 1
      return 0 ;;
  esac
  if is_disposable "$p" || in_repo_ok "$p"; then
    if [ -L "$p" ]; then
      # Deleting the LINK is safe; traversing it (trailing slash) is not.
      [ "$trail" = 1 ] && return 1
      phys_ok "${p%/*}" || return 1
      return 0
    fi
    phys_ok "$p" || return 1
    return 0
  fi
  return 1
}

# ── Command analyzers ────────────────────────────────────────────────────────

analyze_rm() {  # $1=ctx, rest = argv after rm/rmdir. Every non-flag arg must be destroyable.
  local ctx="$1" t npaths=0 ddash=0
  shift
  for t in "$@"; do
    if [ "$ddash" = 0 ]; then
      case "$t" in
        --) ddash=1; continue ;;
        -*) continue ;;
      esac
    fi
    dest_path_ok "$t" "$ctx" || return 1
    npaths=$((npaths + 1))
  done
  [ "$npaths" -ge 1 ]
}

analyze_git() {  # $1=cwd, rest = argv after `git`
  local ctx="" cwd_="$1" sub="" t del=0 hard=0 npaths=0
  shift
  # Global flags: -C <path> (once), -c <k=v>; anything exotic falls through.
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -C)
        [ -n "$ctx" ] && return 1
        [ "$#" -ge 2 ] || return 1
        ctx="$2"; shift 2 ;;
      -c)
        [ "$#" -ge 2 ] || return 1
        shift 2 ;;
      --git-dir*|--work-tree*|--exec-path*) return 1 ;;
      -*) shift ;;
      *) sub="$1"; shift; break ;;
    esac
  done
  [ -n "$sub" ] || return 1
  if [ -n "$ctx" ]; then
    case "$ctx" in
      /*|"~"*|'$'*) : ;;
      *) [ -n "$cwd_" ] || return 1; ctx="${cwd_%/}/$ctx" ;;
    esac
  else
    ctx="$cwd_"
  fi
  [ -n "$ctx" ] || return 1
  trusted_dir "$ctx" || return 1
  ctx="$(expand_prefix "$ctx")"
  case "$sub" in
    push)
      for t in "$@"; do
        case "$t" in
          --force|--force-with-lease*|-f|-d|--delete) return 1 ;;
          +*|:*) return 1 ;;
        esac
      done
      return 0 ;;
    worktree)
      [ "$#" -ge 1 ] || return 1
      case "$1" in
        remove|move)
          shift
          for t in "$@"; do
            case "$t" in -*) continue ;; esac
            dest_path_ok "$t" "$ctx" || return 1
            npaths=$((npaths + 1))
          done
          [ "$npaths" -ge 1 ]; return $? ;;
        list|prune|add) return 0 ;;
        *) return 1 ;;
      esac ;;
    branch)
      for t in "$@"; do
        case "$t" in -D|-d|--delete) del=1 ;; esac
      done
      if [ "$del" = 1 ]; then
        for t in "$@"; do
          case "$t" in -*) continue ;; main|master) return 1 ;; esac
        done
      fi
      return 0 ;;
    reset)
      for t in "$@"; do
        case "$t" in --hard) hard=1 ;; esac
      done
      if [ "$hard" = 1 ]; then
        is_disposable "$ctx" || return 1
      fi
      return 0 ;;
    clean)
      is_disposable "$ctx" || return 1
      for t in "$@"; do
        case "$t" in -*) continue ;; esac
        dest_path_ok "$t" "$ctx" || return 1
      done
      return 0 ;;
    *)
      # Any other git verb in a trusted ctx — parity with what cd-chains get.
      return 0 ;;
  esac
}

tokenize() {  # quote-aware split of $1 into TOKENS[]; return 1 if unjudgeable
  TOKENS=()
  local t
  # Single-quote + $ combinations diverge between shell semantics and our
  # tokenizer (a quoted $VAR would NOT expand in the shell) — refuse to judge.
  case "$1" in *"'"*'$'*|*'$'*"'"*) return 1 ;; esac
  while IFS= read -r t; do
    TOKENS[${#TOKENS[@]}]="$t"
  done < <(printf '%s' "$1" | xargs printf '%s\n' 2>/dev/null) || return 1
  [ "${#TOKENS[@]}" -gt 0 ]
}

analyze_clause() {  # one simple command in context $2; 0 = safe to approve
  local clause="$1" ctx="$2"
  case "$clause" in *';'*|*'|'*|*'&'*|*'<'*|*'>'*|*'`'*|*'$('*) return 1 ;; esac
  clause="$(printf '%s' "$clause" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  [ -n "$clause" ] || return 0
  if ! printf '%s\n' "$clause" | grep -Eiq "$SOFT_RE"; then
    return 0  # non-destructive clause in a trusted dir — same trust as today
  fi
  tokenize "$clause" || return 1
  [ "${#TOKENS[@]}" -ge 2 ] || return 1
  case "${TOKENS[0]}" in
    rm|rmdir) analyze_rm "$ctx" "${TOKENS[@]:1}" ;;
    git) analyze_git "$ctx" "${TOKENS[@]:1}" ;;
    *) return 1 ;;
  esac
}

# ── cd-chain branch (the original design; destructive tails now analyzed) ────
case "$cmd" in
  cd\ *)
    first="$(printf '%s' "$cmd" | head -1)"
    target="$(printf '%s' "$first" | sed -E 's/^cd[[:space:]]+//; s/[[:space:]]*(&&|;).*$//')"
    tail_cmd=""
    case "$first" in
      *"&&"*) tail_cmd="${first#*&&}" ;;
      *";"*)  tail_cmd="${first#*;}" ;;
    esac
    tail_cmd="$(printf '%s' "$tail_cmd" | sed -E 's/^[[:space:]]+//')"
    target="${target%\"}"; target="${target#\"}"
    target="${target%\'}"; target="${target#\'}"

    allow=0
    # Known-trusted env-var prefixes: their value always resolves in-tree.
    case "$target" in
      '$CLAUDE_JOB_DIR'|'$CLAUDE_JOB_DIR/'*|'${CLAUDE_JOB_DIR}'|'${CLAUDE_JOB_DIR}/'*) allow=1 ;;
      '$CLAUDE_PROJECT_DIR'|'$CLAUDE_PROJECT_DIR/'*|'${CLAUDE_PROJECT_DIR}'|'${CLAUDE_PROJECT_DIR}/'*) allow=1 ;;
    esac
    if [ "$allow" = 0 ]; then
      if trusted_dir "$target"; then
        allow=1
      else
        case "$target" in
          /*) : ;;      # foreign absolute path -> stays protected
          *'$'*) : ;;   # unresolved variable -> stays protected
          *..*) : ;;    # path escape -> stays protected
          *) allow=1 ;; # plain in-tree relative target (cwd already trusted)
        esac
      fi
    fi
    [ "$allow" = 1 ] || exit 0

    # Later physical lines: approve only if free of destructive verbs (they
    # used to ride the first line's approval — that was a hole).
    rest="$(printf '%s\n' "$cmd" | tail -n +2)"
    if [ -n "$rest" ] && printf '%s\n' "$rest" | grep -Eiq "$SOFT_RE"; then
      exit 0
    fi

    if [ -n "$tail_cmd" ] && printf '%s\n' "$tail_cmd" | grep -Eiq "$SOFT_RE"; then
      # Destructive tail: analyze every clause with ctx = the cd target.
      case "$tail_cmd" in *';'*|*'|'*|*'`'*|*'$('*|*'<'*|*'>'*) exit 0 ;; esac
      ctx="$(expand_prefix "$target")"
      case "$ctx" in
        /*) : ;;
        *) if [ -n "$cwd" ] && [ -n "$ctx" ]; then ctx="${cwd%/}/$ctx"; else ctx=""; fi ;;
      esac
      clause_fail=0
      while IFS= read -r clause; do
        if ! analyze_clause "$clause" "$ctx"; then
          clause_fail=1
          break
        fi
      done < <(printf '%s\n' "$tail_cmd" | sed 's/&&/\n/g')
      [ "$clause_fail" = 0 ] || exit 0
      emit_allow "Destructive verbs confined to disposable/trusted-repo paths inside a user-owned tree"
    fi
    emit_allow "Trusted cd target inside a user-owned tree (~/Workspace, ~/Code, ~/.claude, worktree, jobs, /tmp) or an in-tree relative path"
    ;;
esac

# ── Standalone branch (no leading cd) ────────────────────────────────────────
case "$cmd" in
  *$'\n'*|*';'*|*'|'*|*'&'*|*'<'*|*'>'*|*'`'*|*'$('*) exit 0 ;;
esac
tokenize "$cmd" || exit 0

case "${TOKENS[0]}" in
  rm|rmdir)
    if [ "${#TOKENS[@]}" -ge 2 ] && analyze_rm "$cwd" "${TOKENS[@]:1}"; then
      emit_allow "Deletion confined to disposable/trusted-repo paths (worktrees, jobs, tmp, in-repo artifacts)"
    fi ;;
  git)
    if [ "${#TOKENS[@]}" -ge 2 ] && analyze_git "$cwd" "${TOKENS[@]:1}"; then
      emit_allow "git in a trusted repo context; destructive forms path-gated to disposable roots"
    fi ;;
  ps)
    emit_allow "Read-only process listing" ;;
  route)
    if [ "${TOKENS[1]:-}" = "-n" ] && [ "${TOKENS[2]:-}" = "get" ]; then
      emit_allow "Read-only route lookup"
    fi ;;
  diskutil)
    case "${TOKENS[1]:-}" in
      list|info) emit_allow "Read-only diskutil query" ;;
    esac ;;
  tmutil)
    case "${TOKENS[1]:-}" in
      status|listbackups|destinationinfo|latestbackup|listlocalsnapshots) emit_allow "Read-only tmutil query" ;;
    esac ;;
  gh)
    if [ "${TOKENS[1]:-}" = "repo" ]; then
      case "${TOKENS[2]:-}" in
        view|list|clone) emit_allow "Read-only gh repo query/clone" ;;
      esac
    fi ;;
esac

exit 0
