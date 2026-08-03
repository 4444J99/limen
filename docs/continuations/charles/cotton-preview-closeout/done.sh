#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
site_dir="$repo_root/docs/continuations/charles/rose-toners-share"
site_path="docs/continuations/charles/rose-toners-share"
route="https://downs-style-rose-toners-preview.ajpadavano.chatgpt.site/cotton"
receipt="$script_dir/evidence.json"

python3 "$repo_root/scripts/tests/downs-style-analysis.test.py"
python3 "$repo_root/scripts/verify-downs-style-archive.py"

cd "$site_dir"
npm test
npm run lint

site_source_manifest_sha256="$(
  git -C "$repo_root" ls-tree -r HEAD -- "$site_path" \
    | LC_ALL=C sort \
    | shasum -a 256 \
    | awk '{print $1}'
)"
python3 - "$receipt" "$route" "$site_source_manifest_sha256" <<'PY'
import json
import sys

receipt = json.load(open(sys.argv[1], encoding="utf-8"))["deployment_receipt"]
expected = {
    "version_number": 11,
    "version_id": "appgprj_6a6f989f3d908191aa52562e2f0c212d~appgver_742cdea5737081919466c2f1c5b77c63",
    "source_commit": "468889391985d2e02c43c9aa07f0dce1cc41aa42",
    "archive_content_hash": "sha256:22f0f908efed030ab383cac581397e8b9fcf98b08548df541bba0f4a93f99fe0",
    "site_source_manifest_sha256": sys.argv[3],
    "route": sys.argv[2],
    "status": "succeeded",
}
for key, value in expected.items():
    if receipt.get(key) != value:
        raise SystemExit(f"deployment receipt mismatch for {key}")
PY

page="$(curl --fail --silent --show-error --location --max-time 20 --retry 2 --retry-all-errors "$route")"
grep -Fq "Is Cotton Good for Summer? What the Label Leaves Out" <<<"$page"
grep -Fq "easiest summer outfit on paper" <<<"$page"
grep -Fq "Private launch package" <<<"$page"
if grep -Fqi "full circle moment" <<<"$page"; then
  echo "superseded opening is present in the deployed preview" >&2
  exit 1
fi

test "$(find "$script_dir/evidence" -maxdepth 1 -type f -name '*.png' | wc -l | tr -d ' ')" = "5"
test -z "$(git -C "$repo_root" status --porcelain)"

printf 'charles-cotton-preview closeout: PASS\n'
