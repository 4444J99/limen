#!/usr/bin/env bash
set -euo pipefail

# Test fixtures must derive behavior from their local setup, never from the
# operator's credentials, signing helpers, ignore files, or interactive editor.
unset LIMEN_API_TOKEN LIMEN_OWNER_TOKEN LIMEN_CLIENT_TOKEN
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
# Git's default global ignore lives under XDG independently of gitconfig.
export XDG_CONFIG_HOME=/dev/null
export GIT_EDITOR=true
export GIT_SEQUENCE_EDITOR=true
export VISUAL=true
export EDITOR=true

exec python3 -m pytest "$@"
