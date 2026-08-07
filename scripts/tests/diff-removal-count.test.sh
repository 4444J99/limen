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
@@ -1,5 +1,3 @@
-real_removal = 1
-
---dash-prefixed-removal
--- sql style comment
+added
DIFF
TRUE_REMOVALS=4
HEADER_RE="^--- (a/|/dev/null)"

# The `-- ` case is the one two successive fixes missed. A source line `-- sql style comment` gains
# the diff's own `-` prefix and renders as `--- sql style comment`, which is byte-indistinguishable
# from a `--- a/<file>` header by prefix alone. Excluding by full header SHAPE is the only filter
# that keeps it.
documented=$(grep '^-' "$TMP/fixture.diff" | grep -vcE "$HEADER_RE")
[ "$documented" = "$TRUE_REMOVALS" ] \
  && pass "the documented pattern counts exactly the $TRUE_REMOVALS real removals" \
  || fail "documented pattern counted $documented, expected $TRUE_REMOVALS"

# EXACT counts, not relations. The comparison table in SKILL.md quotes all four of these numbers, and
# its first draft carried 2 and 4 where the fixture produces 1 and 3 — wrong numbers in a table whose
# whole subject is counting precisely. The earlier version of this gate asserted only "over-counts" /
# "under-counts", which is directionally true of both the right answer and the wrong ones, so it
# certified the table without ever reading it. Each row now has a value, and the row is checked.
expect() { # expect <label> <got> <want>
  [ "$2" = "$3" ] && pass "$1 = $3, as the SKILL.md table states" \
    || fail "$1 = $2 but the SKILL.md table says $3 — table and fixture have drifted"
}

expect "bare '^-'" "$(grep -c '^-' "$TMP/fixture.diff")" 5
expect "'^-[^-]'" "$(grep -cE '^-[^-]' "$TMP/fixture.diff")" 1
expect "loose '^--- ' exclusion" "$(grep '^-' "$TMP/fixture.diff" | grep -vc '^--- ')" 3
expect "full-shape exclusion" "$(grep '^-' "$TMP/fixture.diff" | grep -vcE "$HEADER_RE")" 4

# Direction still asserted, because an exact number that happens to equal TRUE_REMOVALS by accident
# would otherwise read as correct. Both wrong patterns must remain wrong in the direction claimed.
[ "$(grep -c '^-' "$TMP/fixture.diff")" -gt "$TRUE_REMOVALS" ] \
  && pass "the bare '^-' over-counts — noisy, not dangerous" \
  || fail "'^-' no longer over-counts; the fixture stopped exercising the header case"

[ "$(grep -cE '^-[^-]' "$TMP/fixture.diff")" -lt "$TRUE_REMOVALS" ] \
  && pass "'^-[^-]' UNDER-counts — the false negative this recipe must not ship" \
  || fail "'^-[^-]' no longer under-counts; the fixture stopped exercising blank/dash removals"

# The previous fix, which read as exact and was not. Kept so the third iteration cannot be quietly
# reverted to the second.
[ "$(grep '^-' "$TMP/fixture.diff" | grep -vc '^--- ')" -lt "$TRUE_REMOVALS" ] \
  && pass "the loose '^--- ' exclusion still UNDER-counts — it eats the '-- ' removal" \
  || fail "the loose exclusion no longer under-counts; the fixture stopped exercising the '-- ' case"

# Every number above is quoted in SKILL.md's table. If a row is edited to a different value the
# fixture disagrees with, the assertions above fire — but only if the row is actually THERE.
for want in "| \`grep '^-'\` | 5 |" "| **1** |" "| **3** |" "| **4** |"; do
  grep -Fq "$want" "$SKILL" \
    && pass "SKILL.md's table carries the row ${want}" \
    || fail "SKILL.md's table is missing or has changed the row ${want}"
done

# The recipe in the skill file must BE the documented form, not merely mention it. A doc that
# explains the right pattern while its copy-paste block shows the wrong one is worse than silence:
# the block is what gets used.
# `grep -F` on the literal: the pattern being searched for is itself full of regex metacharacters,
# and escaping it twice over is how this assertion would come to test something other than it reads.
grep -Fq 'R="^--- (a/|/dev/null)"' "$SKILL" \
  && pass "SKILL.md's copy-paste block carries the full-shape header exclusion" \
  || fail "SKILL.md's block does not carry the documented pattern"

# Scoped to a RUNNABLE recipe line (one carrying `git diff`), never to any mention. The comparison
# table above deliberately records the loose form as a wrong answer, and a file-wide grep reads that
# record as the defect it warns about. This is the THIRD assertion in this session to need scoping
# for the same reason — "the file must not contain X" is almost never what is meant when the file's
# job is to explain why X is wrong.
grep -qE "git diff.*grep -v '\^--- '" "$SKILL" \
  && fail "SKILL.md still hands out the loose '^--- ' exclusion in a runnable recipe" \
  || pass "no recipe line hands out the loose header exclusion"

# Scoped to a RECIPE line — `git diff … | grep -E '^-[^-]'` — not to any mention of the pattern.
# The prose deliberately names the under-counting form in a comparison table so the trap stays
# recorded; a file-wide grep would flag that explanation as the defect it warns about, which is the
# same over-broad-assertion mistake made once already this session in check-review-harvest.test.sh.
grep -qE "git diff.*grep -E '\^-\[\^-\]'" "$SKILL" \
  && fail "SKILL.md still hands out the under-counting '^-[^-]' pattern in a runnable recipe" \
  || pass "no recipe line hands out the under-counting pattern"

printf '\ndiff-removal-count: %d failure(s)\n' "$fails"
[ "$fails" -eq 0 ]
