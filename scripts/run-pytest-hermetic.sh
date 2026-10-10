#!/usr/bin/env bash
set -euo pipefail

# Test fixtures must derive behavior from their local setup, never from the
# operator's credentials, active workstream identity, signing helpers, ignore
# files, or interactive editor. Scrub the namespace dynamically so a newly
# introduced Limen runtime variable cannot silently become test input.
while IFS= read -r name; do
  unset "$name"
done < <(compgen -A variable LIMEN_)
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
# Git's default global ignore lives under XDG independently of gitconfig.
export XDG_CONFIG_HOME=/dev/null
export GIT_EDITOR=true
export GIT_SEQUENCE_EDITOR=true
export VISUAL=true
export EDITOR=true

# Pin subprocess imports to the same checkout as the test runner. Pytest's
# conftest sys.path applies only to its own interpreter; a child script must not
# fall back to an absent package or an editable install from another worktree.
pytest_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../cli/src" && pwd -P)"
export PYTHONPATH="$pytest_source_root${PYTHONPATH:+:$PYTHONPATH}"

# LIMEN_NOTIFY is an OUTPUT-side safety, not a test input — so it is re-armed AFTER the scrub
# above, and the ordering is the whole point. The scrub is right: a fixture must never read the
# operator's runtime. But osascript is not fixture input; it is an effect that leaves the machine
# and lands on his phone, and scrubbing LIMEN_NOTIFY restores _notify's "1" default — i.e. the
# hermetic wrapper was re-enabling the effector that a caller had deliberately silenced.
#
# This is also the ONLY line that reaches the copies of _notify.py that predate the in-tree gate
# (#1841). A fix committed to main propagates to a stale worktree or a rotated runtime install
# only when that copy is rebased or reaped — but EVERY copy on this host, gated or not, honors
# LIMEN_NOTIFY. You cannot retro-patch old code; you can control the environment it runs in.
export LIMEN_NOTIFY=0

exec python3 -m pytest "$@"
