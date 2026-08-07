#!/usr/bin/env bash
# The removal-counting recipe in .claude/skills/verify/SKILL.md must actually count removals.
#
# WHY A TEST FOR A DOC. That recipe is the clobber check — the thing a session runs to answer "did
# my branch delete someone else's work?" — and it is copied verbatim out of the skill file by every
# session that reads it. A wrong pattern there is not a typo; it is a silent false negative in the
# one check whose entire job is not to have one. Prose cannot hold that line, so this pins it.
#
# BOTH OBVIOUS ONE-LINERS ARE WRONG, IN OPPOSITE DIRECTIONS, and the tidier-looking one is the
# dangerous one:
#
#   grep '^-'          over-counts — a diff's own `--- a/<file>` header starts with a dash
#   grep -E '^-[^-]'   UNDER-counts — a removed BLANK line is a lone `-`, and a removed `--flag`
#                      line renders as `---flag`, so both are silently dropped
#
# Over-counting is noise: you inspect a phantom line and move on. Under-counting hides the clobber.
# The skill file shipped `'^-[^-]'` for exactly one merge before this was caught.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
SKILL="$ROOT/.claude/skills/verify/SKILL.md"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fails=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

# A unified diff carrying all three removal shapes plus the header that fools the naive pattern.
cat > "$TMP/fixture.diff" <<'DIFF'
--- a/foo.py
+++ b/foo.py
@@ -1,4 +1,3 @@
-real_removal = 1
-
---dash-prefixed-removal
+added
DIFF
TRUE_REMOVALS=3

documented=$(grep '^-' "$TMP/fixture.diff" | grep -vc '^--- ')
[ "$documented" = "$TRUE_REMOVALS" ] \
  && pass "the documented pattern counts exactly the $TRUE_REMOVALS real removals" \
  || fail "documented pattern counted $documented, expected $TRUE_REMOVALS"

naive=$(grep -c '^-' "$TMP/fixture.diff")
[ "$naive" -gt "$TRUE_REMOVALS" ] \
  && pass "the bare '^-' over-counts, as documented (got $naive) — noisy, not dangerous" \
  || fail "'^-' no longer over-counts; the fixture stopped exercising the header case"

deflating=$(grep -cE '^-[^-]' "$TMP/fixture.diff")
[ "$deflating" -lt "$TRUE_REMOVALS" ] \
  && pass "'^-[^-]' UNDER-counts (got $deflating) — the false negative this recipe must not ship" \
  || fail "'^-[^-]' no longer under-counts; the fixture stopped exercising blank/dash removals"

# The recipe in the skill file must BE the documented form, not merely mention it. A doc that
# explains the right pattern while its copy-paste block shows the wrong one is worse than silence:
# the block is what gets used.
grep -q "grep '\^-' | grep -v '\^--- '" "$SKILL" \
  && pass "SKILL.md's copy-paste block carries the header-excluding form" \
  || fail "SKILL.md's block does not carry the documented pattern"

# Scoped to a RECIPE line — `git diff … | grep -E '^-[^-]'` — not to any mention of the pattern.
# The prose deliberately names the under-counting form in a comparison table so the trap stays
# recorded; a file-wide grep would flag that explanation as the defect it warns about, which is the
# same over-broad-assertion mistake made once already this session in check-review-harvest.test.sh.
grep -qE "git diff.*grep -E '\^-\[\^-\]'" "$SKILL" \
  && fail "SKILL.md still hands out the under-counting '^-[^-]' pattern in a runnable recipe" \
  || pass "no recipe line hands out the under-counting pattern"

printf '\ndiff-removal-count: %d failure(s)\n' "$fails"
[ "$fails" -eq 0 ]
