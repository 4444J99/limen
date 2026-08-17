#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
site_dir="$repo_root/docs/continuations/charles/rose-toners-share"
route="https://downs-style-rose-toners-preview.ajpadavano.chatgpt.site/cotton"
receipt="$script_dir/evidence.json"

python3 "$repo_root/scripts/tests/downs-style-analysis.test.py"
python3 "$repo_root/scripts/verify-downs-style-archive.py"

cd "$site_dir"
npm ci
npm test
npm run lint

# Version 12 owns the cotton URL. Other private studio routes can move without
# claiming that the complete current studio tree was deployed as version 12.
python3 - "$receipt" "$route" <<'PY'
import json
import sys

receipt = json.load(open(sys.argv[1], encoding="utf-8"))["deployment_receipt"]
expected = {
    "version_number": 12,
    "version_id": "appgprj_6a6f989f3d908191aa52562e2f0c212d~appgver_74b8a360a0e48191925877b122c11787",
    "source_commit": "9a169efaa60e18516e9be8a7948e7a14751f8047",
    "archive_content_hash": "sha256:7c2651a9207663f8d050273830e83806620ccca1bc3afd6d814437e30568a40b",
    "site_source_manifest_sha256": "90c3c92d34252fc8a1138b69d08478326b9ee7fcd2b8247c791c278b7e3dbcb2",
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

expected_evidence=(
  "01-live-rose.png"
  "02-preview-rose.png"
  "03-cotton-desktop.png"
  "04-cotton-mobile-grid.png"
  "05-cotton-final.png"
)
for filename in "${expected_evidence[@]}"; do
  image="$script_dir/evidence/$filename"
  test -s "$image"
  test "$(od -An -tx1 -N8 "$image" | tr -d ' \n')" = "89504e470d0a1a0a"
done
test "$(find "$script_dir/evidence" -maxdepth 1 -type f -name '*.png' | wc -l | tr -d ' ')" = "${#expected_evidence[@]}"

git -C "$repo_root" diff --check
printf 'charles-cotton-preview local predicate: PASS\n'
