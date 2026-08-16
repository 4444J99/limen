#!/usr/bin/env bash
# install-git-hooks.sh — wire repo-local git hooks
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
HOOKS="$ROOT/.git/hooks"

mkdir -p "$HOOKS"
cat > "$HOOKS/pre-push" << 'HOOK_EOF'
#!/usr/bin/env bash
# Verify no .limen-private/ plaintext is tracked and vault integrity before pushing
python3 "$(git rev-parse --show-toplevel)/scripts/private-vault.py" verify || exit 1
HOOK_EOF
chmod +x "$HOOKS/pre-push"
echo "OK: pre-push hook installed"
