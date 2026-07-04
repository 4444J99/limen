#!/usr/bin/env bash
# Regression tests for scripts/cf-wrangler.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WRAPPER="$ROOT/scripts/cf-wrangler.sh"
[ -f "$WRAPPER" ] || { echo "missing wrapper: $WRAPPER" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

make_bin() {
  local path="$1" label="$2"
  mkdir -p "$(dirname "$path")"
  cat > "$path" <<SH
#!/usr/bin/env bash
echo "$label:\$*"
SH
  chmod +x "$path"
}

make_bin "$tmp/project/node_modules/.bin/wrangler" "local"
make_bin "$tmp/global/wrangler" "global"

got="$(
  cd "$tmp/project"
  PATH="$tmp/global:$PATH" LIMEN_ENV="$tmp/missing.env" CLOUDFLARE_API_TOKEN=dummy bash "$WRAPPER" deploy
)"
[ "$got" = "local:deploy" ] || {
  echo "FAIL: expected local wrangler before global, got: $got" >&2
  exit 1
}

rm -rf "$tmp/project/node_modules"
got="$(
  cd "$tmp/project"
  PATH="$tmp/global:$PATH" LIMEN_ENV="$tmp/missing.env" CLOUDFLARE_API_TOKEN=dummy bash "$WRAPPER" deploy
)"
[ "$got" = "global:deploy" ] || {
  echo "FAIL: expected global fallback, got: $got" >&2
  exit 1
}

set +e
missing="$(
  cd "$tmp/project"
  PATH="$tmp/global:$PATH" LIMEN_ENV="$tmp/missing.env" bash "$WRAPPER" deploy 2>&1
)"
status=$?
set -e
[ "$status" = 3 ] || {
  echo "FAIL: expected missing token exit 3, got: $status" >&2
  echo "$missing" >&2
  exit 1
}
case "$missing" in
  *"wrangler login"*) ;;
  *) echo "FAIL: missing-token guidance should explain no wrangler login path" >&2; echo "$missing" >&2; exit 1 ;;
esac

echo "cf-wrangler regression test PASSED"
