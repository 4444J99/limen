#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
site_dir="$repo_root/docs/continuations/charles/rose-toners-share"
route="https://downs-style-rose-toners-preview.ajpadavano.chatgpt.site/cotton"

cd "$site_dir"
npm test
npm run lint

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
