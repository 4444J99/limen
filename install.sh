#!/usr/bin/env bash
# limen — universal agent task intake
# install.sh: idempotent one-liner installer
#
#   curl -fsSL https://raw.githubusercontent.com/4444J99/limen/main/install.sh | bash
#
# Clones the limen repo, creates ~/limen symlink, installs Python CLI,
# and prompts for env var setup.
set -euo pipefail

LIMEN_SOURCE="${LIMEN_SOURCE:-https://github.com/4444J99/limen.git}"
LIMEN_TARGET="${LIMEN_TARGET:-$HOME/Workspace/limen}"
LIMEN_LINK="${LIMEN_LINK:-$HOME/limen}"
LIMEN_CLI="${LIMEN_TARGET}/cli"

echo "==> limen installer"

# 1. Clone or pull
if [[ -d "$LIMEN_TARGET/.git" ]]; then
  echo "  repo exists at $LIMEN_TARGET — pulling latest"
  git -C "$LIMEN_TARGET" pull --ff-only
else
  echo "  cloning into $LIMEN_TARGET"
  mkdir -p "$(dirname "$LIMEN_TARGET")"
  git clone "$LIMEN_SOURCE" "$LIMEN_TARGET"
fi

# 2. Create symlink
if [[ -L "$LIMEN_LINK" ]]; then
  echo "  symlink $LIMEN_LINK already exists"
elif [[ -e "$LIMEN_LINK" ]]; then
  echo "  WARNING: $LIMEN_LINK exists and is not a symlink — skipping"
else
  ln -s "$LIMEN_TARGET" "$LIMEN_LINK"
  echo "  symlink $LIMEN_LINK -> $LIMEN_TARGET"
fi

# 3. Install Python CLI
if command -v python3 &>/dev/null; then
  echo "  installing Python CLI"
  python3 -m venv "${LIMEN_CLI}/.venv"
  "${LIMEN_CLI}/.venv/bin/pip" install --quiet -e "$LIMEN_CLI"
  echo "  CLI installed at ${LIMEN_CLI}/.venv/bin/limen"
else
  echo "  WARNING: python3 not found — skipping CLI install"
fi

# 4. Env var setup
LIMEN_ENV_LINE='export LIMEN_ROOT="$HOME/limen"'
ZSHRC="${ZDOTDIR:-$HOME}/.zshenv"
if grep -q 'LIMEN_ROOT' "$ZSHRC" 2>/dev/null; then
  echo "  LIMEN_ROOT already set in $ZSHRC"
else
  echo "$LIMEN_ENV_LINE" >>"$ZSHRC"
  echo "  added LIMEN_ROOT to $ZSHRC (restart shell or 'source $ZSHRC')"
fi

echo "==> done"
echo "  Run: source ${ZSHRC} && limen status"
