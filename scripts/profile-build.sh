#!/usr/bin/env bash
# profile-build.sh — render the full provable, self-hosted 4444J99 profile into OUT.
#
# One driver for both the local run and the GitHub Action: collect live facts + render the
# self-hosted SVGs (+ provability manifest), harvest every follow's techniques, project the
# README from the owned positioning, then VERIFY the whole page is provable & self-hosted.
# Any step failing aborts before a commit — a broken run keeps the prior good profile.
#
#   scripts/profile-build.sh _profile-build      # OUT defaults to $LIMEN_PROFILE_OUT or _profile-build
set -euo pipefail

OUT="${1:-${LIMEN_PROFILE_OUT:-_profile-build}}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

python3 "$HERE/scripts/profile-visuals.py" --out "$OUT"
python3 "$HERE/scripts/follow-harvest-organ.py" --out "$OUT"
python3 "$HERE/scripts/sync-readme.py" --out "$OUT"
python3 "$HERE/scripts/profile-verify.py" --out "$OUT"
