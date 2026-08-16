#!/usr/bin/env bash
# private-vault-batch.sh — package and vault each .limen-private/ subtree.
#
# Produces artifact-005 through artifact-018 in institutio/vault/.
# Requires: gpg with the operator private key available in the keyring.
# Usage:    bash scripts/private-vault-batch.sh
#
# Idempotent: already-vaulted artifact IDs are skipped (vault add refuses duplicates).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PRIV="$ROOT/.limen-private"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ ! -d "$PRIV" ]]; then
  echo "ERROR: .limen-private/ not found at $PRIV" >&2
  exit 1
fi

vault_add() {
  local artifact_id="$1"
  local tarball="$2"
  python3 "$ROOT/scripts/private-vault.py" add --apply \
    --artifact-id "$artifact_id" "$tarball"
}

# Parallel arrays — order must match.
ARTIFACT_IDS=(
  artifact-005
  artifact-006
  artifact-007
  artifact-008
  artifact-009
  artifact-010
  artifact-011
  artifact-012
  artifact-013
  artifact-014
  artifact-015
  artifact-016
  artifact-017
  artifact-018
)

# Paths relative to $PRIV. Space-separated for multi-path entries.
SUBTREES=(
  "async-runs"
  "career-tracker"
  "decorum"
  "email-ask-audit"
  "link-health"
  "mail-story"
  "receipts"
  "recovery-bundles"
  "reports"
  "security"
  "session-corpus/lifecycle"
  "session-corpus/local-memory"
  "session-corpus/corpus-command-center session-corpus/host-mutations session-corpus/objects session-corpus/omega-substrate-literal session-corpus/screenshots"
  "session-corpus/prompt-atoms"
)

TOTAL="${#ARTIFACT_IDS[@]}"

for i in "${!ARTIFACT_IDS[@]}"; do
  artifact_id="${ARTIFACT_IDS[$i]}"
  # shellcheck disable=SC2206
  subtree_paths=(${SUBTREES[$i]})
  num=$((i + 1))

  # Skip already-vaulted IDs
  if grep -q "\"${artifact_id}\"" "$ROOT/institutio/vault/manifest.jsonl" 2>/dev/null; then
    echo "[$num/$TOTAL] SKIP $artifact_id — already in manifest"
    continue
  fi

  # Verify source paths exist
  all_exist=true
  for p in "${subtree_paths[@]}"; do
    if [[ ! -e "$PRIV/$p" ]]; then
      echo "[$num/$TOTAL] WARN $artifact_id — source missing: $p, skipping" >&2
      all_exist=false
    fi
  done
  if [[ "$all_exist" == "false" ]]; then
    continue
  fi

  tarball="$TMP/${artifact_id}.tar.gz"
  echo "[$num/$TOTAL] Packaging $artifact_id (${subtree_paths[*]})"

  tar_args=()
  for p in "${subtree_paths[@]}"; do
    tar_args+=(-C "$PRIV" "$p")
  done
  tar -czf "$tarball" "${tar_args[@]}"

  size="$(du -sh "$tarball" | cut -f1)"
  echo "    compressed: $size — encrypting..."
  vault_add "$artifact_id" "$tarball"
  echo "    OK: $artifact_id -> institutio/vault/${artifact_id}.gpg"

  # Remove tarball immediately to keep temp space bounded
  rm -f "$tarball"
done

echo ""
echo "==> Batch complete. Next:"
echo "    git add institutio/vault/ .gitattributes scripts/private-vault.py scripts/private-vault-batch.sh"
