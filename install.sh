#!/usr/bin/env bash
# limen — universal agent task intake
# install.sh: idempotent one-liner installer
#
#   curl -fsSL https://raw.githubusercontent.com/4444J99/limen/main/install.sh | bash
#
# Clones the limen repo, creates ~/limen symlink, installs Python CLI,
# and optionally installs legacy host PATH/wrapper conveniences.
set -euo pipefail

HOST_MUTATION="${LIMEN_INSTALL_HOST_MUTATION:-0}"

usage() {
  cat <<'EOF'
Usage: install.sh [--host-mutation]

Default install clones Limen and installs the Python CLI without editing shell
startup files or adding ~/.local/bin wrappers.

Options:
  --host-mutation   Opt in to legacy ~/.zshenv PATH edits and ~/.local/bin wrappers.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host-mutation | --legacy-host-mutation)
      HOST_MUTATION=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

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

# 4. Optional legacy host mutation
LIMEN_BIN="${LIMEN_CLI}/.venv/bin"
USER_BIN="${HOME}/.local/bin"
LIMEN_ENV_LINE='export LIMEN_ROOT="$HOME/limen"'
LIMEN_PATH_LINE="export PATH=\"${USER_BIN}:${LIMEN_BIN}:\$PATH\""
ZSHRC="${ZDOTDIR:-$HOME}/.zshenv"

if [[ "$HOST_MUTATION" == "1" || "$HOST_MUTATION" == "true" ]]; then
  mkdir -p "$USER_BIN"
  cat >"${USER_BIN}/limen" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${LIMEN_BIN}/limen" "\$@"
EOF
  cat >"${USER_BIN}/workstream" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${LIMEN_BIN}/limen" workstream "\$@"
EOF
  chmod +x "${USER_BIN}/limen" "${USER_BIN}/workstream"
  echo "  installed wrappers at ${USER_BIN}/limen and ${USER_BIN}/workstream"
  if grep -q 'LIMEN_ROOT' "$ZSHRC" 2>/dev/null; then
    echo "  LIMEN_ROOT already set in $ZSHRC"
  else
    echo "$LIMEN_ENV_LINE" >>"$ZSHRC"
    echo "  added LIMEN_ROOT to $ZSHRC"
  fi
  if grep -qF "$LIMEN_BIN" "$ZSHRC" 2>/dev/null; then
    echo "  limen PATH already set in $ZSHRC"
  else
    echo "$LIMEN_PATH_LINE" >>"$ZSHRC"
    echo "  added limen to PATH in $ZSHRC (restart shell or 'source $ZSHRC')"
  fi
else
  echo "  skipped host PATH/wrapper mutation (use --host-mutation to opt in)"
fi

echo "==> done"
echo "  Run: ${LIMEN_BIN}/limen status"
echo "  Start a workstream: ${LIMEN_BIN}/limen workstream --prompt 'objective and constraints' limen my-workstream"
