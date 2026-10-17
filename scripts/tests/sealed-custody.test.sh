#!/usr/bin/env bash
# sealed-custody.test.sh — hermetic regression for scripts/sealed-custody.py (two-device arca-sealed custody).
#
# Why it exists: the tool's whole value is a chain of claims — the ciphertext on each device matches its
# manifest WITHOUT the key, the bundle restores byte-for-byte via the Keychain key AND via the escrow (op)
# key, no plaintext survives under the staging root, and the tracked receipt leaks no device id, absolute
# path, or member digest. A regression in any link would silently weaken custody evidence. Hermetic: PATH
# stubs stand in for `security` and `op` (fixed throwaway key), device ids come from the test-only override
# (LIMEN_SEALED_CUSTODY_TEST=1), and the staging root is a temp dir. Nothing touches the real Keychain, the
# real 1Password, diskutil, or any real volume.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
TOOL="$ROOT/scripts/sealed-custody.py"

# The tool imports limen (rfc8785, pydantic): pick the first interpreter that can.
PY=""
for candidate in "${LIMEN_SEALED_CUSTODY_PYTHON:-}" "${LIMEN_GATE_PYTHON:-}" "$ROOT/cli/.venv/bin/python" \
  "${LIMEN_ROOT:-/nonexistent}/cli/.venv/bin/python" "$HOME/Workspace/limen/cli/.venv/bin/python" \
  python3.13 python3 python3.12 python3.11 python3.14; do
  [ -n "$candidate" ] || continue
  if "$candidate" -c 'import rfc8785, pydantic' >/dev/null 2>&1; then PY="$candidate"; break; fi
done
[ -n "$PY" ] || { echo "FAIL: no python with rfc8785+pydantic (set LIMEN_SEALED_CUSTODY_PYTHON)" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

pass=0; fail=0
ok() { echo "  ok   $1"; pass=$((pass+1)); }
bad() { echo "  FAIL $1"; fail=$((fail+1)); }
expect_rc() { # expect_rc <want> <label> <cmd...>
  local want="$1" label="$2" rc=0; shift 2
  "$@" >"$work/last.out" 2>&1 || rc=$?
  if [ "$rc" = "$want" ]; then ok "$label"; else bad "$label (want exit $want got $rc)"; sed 's/^/    /' "$work/last.out"; fi
}
mode() { stat -f '%Lp' "$1" 2>/dev/null || stat -c '%a' "$1"; }

# ── stubs: a fixed throwaway key; marker files prove which source answered ──
KEY="$(printf 'ab%.0s' $(seq 1 32))"
mkdir -p "$work/bin" "$work/markers"
cat > "$work/bin/security" <<SH
#!/usr/bin/env bash
case "\${1:-}" in
  find-generic-password) : > "$work/markers/security"; printf '%s\n' "$KEY" ;;
  *) exit 1 ;;
esac
SH
cat > "$work/bin/op" <<SH
#!/usr/bin/env bash
[ -z "\${OP_SERVICE_ACCOUNT_TOKEN:-}" ] || exit 9
[ "\${1:-}" = read ] || exit 1
: > "$work/markers/op"
printf '%s\n' "$KEY"
SH
chmod +x "$work/bin/security" "$work/bin/op"
export PATH="$work/bin:$PATH"
export OP_SERVICE_ACCOUNT_TOKEN="stub-token-must-be-stripped"
export ARCA_KEY_SERVICE="test-sealed-custody"
export LIMEN_CUSTODY_STAGING_ROOT="$work/staging"
export LIMEN_SEALED_CUSTODY_TEST=1
reset_markers() { rm -rf "$work/markers"; mkdir -p "$work/markers"; }

tool() { "$PY" -I "$TOOL" "$@"; }
DEV_A="device_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
DEV_B="device_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

# ── fixture: a tiny source tree ──
src="$work/src/bundle"
mkdir -p "$src/sub" "$work/devA" "$work/devB"
printf 'alpha\n' > "$src/a.txt"
printf 'bravo bravo\n' > "$src/b.bin"
printf 'charlie\n' > "$src/sub/c.txt"

export LIMEN_SEALED_CUSTODY_DEVICE_ID_OVERRIDE="$DEV_A"
expect_rc 0 "seal onto device A" tool seal --source "$src" --replica-root "$work/devA" --run run-001 --label test-bundle
expect_rc 1 "seal refuses an existing run dir" tool seal --source "$src" --replica-root "$work/devA" --run run-001
export LIMEN_SEALED_CUSTODY_DEVICE_ID_OVERRIDE="$DEV_B"
expect_rc 0 "seal onto device B" tool seal --source "$src" --replica-root "$work/devB" --run run-001 --label test-bundle
unset LIMEN_SEALED_CUSTODY_DEVICE_ID_OVERRIDE

[ "$(mode "$work/devA/run-001")" = "700" ] && ok "run dir is 0700" || bad "run dir mode"
[ "$(mode "$work/devA/run-001/bundle.tar.enc")" = "600" ] && ok "ciphertext is 0600" || bad "ciphertext mode"
[ "$(mode "$work/devA/run-001/manifest.json")" = "600" ] && ok "manifest is 0600" || bad "manifest mode"

# ── key-less verify: no key source is consulted, still passes ──
reset_markers
expect_rc 0 "verify A (key-less)" tool verify --replica "$work/devA/run-001"
expect_rc 0 "verify B (key-less)" tool verify --replica "$work/devB/run-001"
if [ ! -e "$work/markers/security" ] && [ ! -e "$work/markers/op" ]; then ok "verify never asked for a key"; else bad "verify touched a key source"; fi

# ── corruption: flip one byte of a copy → verify exits 1, restore refuses ──
cp -R "$work/devA/run-001" "$work/corrupt"
"$PY" -I - "$work/corrupt/bundle.tar.enc" <<'PY'
import sys

path = sys.argv[1]
data = bytearray(open(path, "rb").read())
data[len(data) // 2] ^= 0x01
open(path, "wb").write(data)
PY
expect_rc 1 "verify detects a corrupted byte" tool verify --replica "$work/corrupt"
expect_rc 1 "restore refuses a corrupted ciphertext" tool restore --replica "$work/corrupt"

# ── receipt before any restore must refuse ──
expect_rc 1 "receipt refuses unrestored replicas" tool receipt \
  --replica "$work/devA/run-001" --replica "$work/devB/run-001" \
  --out "$work/private/early.json" --tracked-out "$work/tracked/early.json"

# ── restore: Keychain key, then escrow (op) key ──
reset_markers
expect_rc 0 "restore A via keychain" tool restore --replica "$work/devA/run-001" --key-source keychain
if [ -e "$work/markers/security" ] && [ ! -e "$work/markers/op" ]; then ok "keychain restore used only the Keychain"; else bad "keychain restore key source"; fi
reset_markers
expect_rc 0 "restore B via op escrow" tool restore --replica "$work/devB/run-001" --key-source op
if [ -e "$work/markers/op" ] && [ ! -e "$work/markers/security" ]; then ok "op restore never touched the Keychain"; else bad "op restore key source"; fi
if grep -q "$KEY" "$work/last.out"; then bad "restore output leaked the key"; else ok "restore output carries no key"; fi

# ── no plaintext remains under the staging root ──
leftover="$(find "$work/staging" -mindepth 1 | wc -l | tr -d ' ')"
if [ "$leftover" = "0" ]; then ok "no plaintext or scratch left under staging root"; else bad "staging root holds $leftover entries"; fi

# ── receipt ──
expect_rc 0 "receipt from two restored devices" tool receipt \
  --replica "$work/devA/run-001" --replica "$work/devB/run-001" \
  --out "$work/private/custody.json" --tracked-out "$work/tracked/receipt.json" --retirement-lever L-TEST
if "$PY" -I - "$ROOT" "$work" <<'PY'
import hashlib
import json
import sys

root, work = sys.argv[1:3]
sys.path.insert(0, f"{root}/cli/src")
from limen.prima_materia import CustodyReceiptV1

tracked_text = open(f"{work}/tracked/receipt.json").read()
tracked = json.loads(tracked_text)
manifest = json.load(open(f"{work}/devA/run-001/manifest.json"))
assert tracked["schema"] == "limen.sealed_custody_receipt.tracked.v1"
assert tracked["independent_device_count"] == 2, tracked
assert tracked["restore_verified"] == [True, True]
assert sorted(tracked["key_sources"]) == ["keychain", "op"]
assert tracked["member_count"] == 3 and tracked["plaintext_retained"] is False
assert tracked["retirement_lever"] == "L-TEST" and tracked["label"] == "test-bundle"
for forbidden in ("device_aaaa", "device_bbbb", work, "/Users", "/var/", "/tmp/"):
    assert forbidden not in tracked_text, forbidden
for member in manifest["members"]:
    assert member["sha256"] not in tracked_text
private_bytes = open(f"{work}/private/custody.json", "rb").read()
assert tracked["custody_receipt_sha256"] == hashlib.sha256(private_bytes).hexdigest()
receipt = CustodyReceiptV1.model_validate_json(private_bytes)
assert len(set(receipt.independent_device_ids)) == 2
assert len(receipt.restoration_proofs) == 2
PY
then ok "tracked receipt is redacted; private receipt validates (2 devices)"; else bad "receipt contents"; fi

# ── same physical device twice must not make a receipt ──
expect_rc 1 "receipt refuses one device used twice" tool receipt \
  --replica "$work/devA/run-001" --replica "$work/devA/run-001" \
  --out "$work/private/dup.json" --tracked-out "$work/tracked/dup.json"

echo
if [ "$fail" -eq 0 ]; then
  echo "sealed-custody.test.sh: PASS ($pass checks)"
else
  echo "sealed-custody.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
