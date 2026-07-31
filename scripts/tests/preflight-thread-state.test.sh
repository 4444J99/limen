#!/usr/bin/env bash
# Hermetic exit-contract matrix for scripts/preflight-thread-state.py — the ground-truth predicate
# behind the `github.comment` outbound effector.
#
# WHY THIS FILE IS THE DELIVERABLE, NOT THE SCRIPT: the predicate's whole value is its exit code.
# 0 opens an outward gate; 1 and 77 hold it shut. A predicate that returns 0 when it could not look
# is indistinguishable from the advisory hook in ~/.claude/settings.json that asks "did you read the
# thread?" and is answered "yes" by the thing being audited. So SKIP-still-denies and
# ack-is-target-bound are tested first and hardest.
#
# HERMETIC: a fake `gh` on PATH serving JSON fixtures. No network, no auth, no real thread.
# Mirrors the fixture style of outbound-preflight-guard.test.sh and paused-coherence.test.sh
# (which shims `bash` the same way).
#
# ACK SAFETY: every fixture uses the repo `fixture-owner/fixture-repo`, which cannot exist, so an
# acknowledgement minted here can never satisfy a gate on a REAL thread — the ack is keyed on a
# digest of `owner/repo#N`. The trap still removes them; belt and braces, because an ack file that
# outlived its test would be a gate this repo opened against itself.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
PREDICATE="$ROOT/scripts/preflight-thread-state.py"
REGISTRY="$ROOT/institutio/governance/outbound-effectors.yaml"
TMP="$(mktemp -d)"
FIXTURE_REPO="fixture-owner/fixture-repo"

cleanup() {
  # Remove only the acks this run could have minted, by recomputing their digests.
  for n in 1 2 3 4 5 6; do
    d="$(python3 -c "
import hashlib,sys
print(hashlib.sha256(f'$FIXTURE_REPO#{sys.argv[1]}'.strip().lower().encode()).hexdigest()[:16])" "$n" 2>/dev/null)"
    [ -n "$d" ] && rm -f "$ROOT/logs/preflight-acks/github.comment.$d.json"
  done
  rm -rf "$TMP"
}
trap cleanup EXIT

fails=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

mkdir -p "$TMP/bin" "$TMP/fixtures"

# ── the fake gh ───────────────────────────────────────────────────────────────────────────────
# Maps an API endpoint to $GH_FIXTURES/<sanitized>.json. Honours --slurp by wrapping the fixture
# array in an outer array (that is exactly what real `gh api --paginate --slurp` returns), and
# refuses --slurp entirely when GH_NO_SLURP=1 so the single-page fallback path is exercised.
cat > "$TMP/bin/gh" <<'FAKE'
#!/usr/bin/env python3
import json, os, re, sys

args = sys.argv[1:]
fixtures = os.environ["GH_FIXTURES"]

def out(obj):
    sys.stdout.write(json.dumps(obj)); sys.exit(0)

if os.environ.get("GH_BROKEN") == "1":
    sys.stderr.write("HTTP 401: Bad credentials\n"); sys.exit(1)

if args[:2] == ["repo", "view"]:
    sys.stdout.write(os.environ.get("GH_AMBIENT_REPO", "fixture-owner/fixture-repo") + "\n")
    sys.exit(0)

if args[0] != "api":
    sys.stderr.write(f"fake gh: unsupported {args}\n"); sys.exit(1)

slurp = "--slurp" in args
if slurp and os.environ.get("GH_NO_SLURP") == "1":
    sys.stderr.write("unknown flag: --slurp\n"); sys.exit(1)

endpoint = [a for a in args[1:] if not a.startswith("-")][-1]
route = endpoint.split("?")[0]           # the query must be stripped BEFORE the segment test below
key = re.sub(r"[^A-Za-z0-9]+", "_", route).strip("_")
path = os.path.join(fixtures, key + ".json")
if not os.path.exists(path):
    # An absent list fixture means "this thread has none of these"; an absent HEAD is a 404.
    if route.rstrip("/").split("/")[-1] in {"comments", "reviews"}:
        out([[]] if slurp else [])
    sys.stderr.write(f"HTTP 404: Not Found ({endpoint})\n"); sys.exit(1)

payload = json.load(open(path))
out([payload] if slurp and isinstance(payload, list) else payload)
FAKE
chmod +x "$TMP/bin/gh"

fixture() {  # fixture <endpoint> <json>
  key="$(python3 -c "
import re,sys; print(re.sub(r'[^A-Za-z0-9]+','_',sys.argv[1]).strip('_'))" "$1")"
  printf '%s' "$2" > "$TMP/fixtures/$key.json"
}

run() {  # run <extra-env...> -- <args...>  -> prints output, sets RC
  local env_pairs=() ; while [ "$1" != "--" ]; do env_pairs+=("$1"); shift; done; shift
  OUT="$(env PATH="$TMP/bin:$PATH" GH_FIXTURES="$TMP/fixtures" "${env_pairs[@]}" \
    python3 "$PREDICATE" "$@" 2>&1)"
  RC=$?
}

echo "preflight-thread-state matrix"

# ── 0. the predicate exists at the path the registry declares ─────────────────────────────────
# This IS check-runner-coverage finding C. The gate could not be armed while this failed: the guard
# fails CLOSED inside its match, so a missing predicate denies every `gh pr comment`.
[ -f "$PREDICATE" ] && pass "the predicate declared by outbound-effectors.yaml exists" \
  || fail "predicate missing — arming github.comment would deny every matching command"
grep -q 'preflight-thread-state.py' "$REGISTRY" \
  && pass "the registry still points at this file" \
  || fail "registry no longer references preflight-thread-state.py"

# ── 1. SKIP still DENIES — the single most important row ───────────────────────────────────────
run GH_BROKEN=1 -- --number 1 --repo "$FIXTURE_REPO"
[ "$RC" = "77" ] && pass "an API failure exits 77 (SKIP), never 0" \
  || fail "API failure exited $RC — 'I could not look' must never open the gate"
printf '%s' "$OUT" | grep -q "is not 'there is nothing there'" \
  && pass "the SKIP message says why silence is not safety" || fail "SKIP message lost its reason"

run PATH_OVERRIDE=1 -- --number 0 --repo "$FIXTURE_REPO"
[ "$RC" = "77" ] && pass "a non-positive number exits 77" || fail "number 0 exited $RC"

run GH_AMBIENT_REPO=bad-form -- --number 1 --repo "not-a-repo"
[ "$RC" = "77" ] && pass "a malformed --repo exits 77" || fail "malformed --repo exited $RC"

# gh absent from PATH entirely (the most likely real-world SKIP). The interpreter is pinned to the
# resolved python3 and PATH is emptied — an earlier version passed PATH=/usr/bin:/bin, which on
# macOS silently selected the CommandLineTools 3.9 stub and died on `from datetime import UTC`.
# That is a test measuring its own environment instead of the predicate.
PYBIN="$(command -v python3)"
mkdir -p "$TMP/nogh"
OUT="$(env PATH="$TMP/nogh" GH_FIXTURES="$TMP/fixtures" \
  "$PYBIN" "$PREDICATE" --number 1 --repo "$FIXTURE_REPO" 2>&1)"; RC=$?
[ "$RC" = "77" ] && pass "gh absent from PATH exits 77" || fail "gh-absent exited $RC: $OUT"

# ── 2. an empty thread PASSES (there is nothing to talk over) ──────────────────────────────────
fixture "repos/$FIXTURE_REPO/issues/1" \
  '{"number":1,"title":"empty thread","state":"open"}'
run X=1 -- --number 1 --repo "$FIXTURE_REPO"
[ "$RC" = "0" ] && pass "a thread with no comments PASSES" || fail "empty thread exited $RC: $OUT"
printf '%s' "$OUT" | grep -q "records: 0 comment" \
  && pass "scope line reports the record count before the verdict (Data Grounding)" \
  || fail "no record count in the output"

# ── 3. a thread with comments FAILS, and prints them ──────────────────────────────────────────
fixture "repos/$FIXTURE_REPO/issues/2" \
  '{"number":2,"title":"live conversation","state":"open"}'
fixture "repos/$FIXTURE_REPO/issues/2/comments" \
  '[{"id":9001,"body":"I already answered this — do not repeat it.","created_at":"2026-07-30T10:00:00Z","html_url":"https://x/1","user":{"login":"maintainer","type":"User"}},
    {"id":9002,"body":"nit: typo","created_at":"2026-07-30T11:00:00Z","html_url":"https://x/2","user":{"login":"coderabbitai[bot]","type":"Bot"}}]'
run X=1 -- --number 2 --repo "$FIXTURE_REPO"
[ "$RC" = "1" ] && pass "an unread thread FAILS (exit 1)" || fail "unread thread exited $RC: $OUT"
printf '%s' "$OUT" | grep -q "issue:9001" && pass "prints the comment identity to acknowledge" || fail "no identity printed"
printf '%s' "$OUT" | grep -q "I already answered this" \
  && pass "prints the comment BODY, so the decision is made with it in hand" || fail "body not printed"
printf '%s' "$OUT" | grep -q "maintainer" && pass "names the author" || fail "author not named"
printf '%s' "$OUT" | grep -q "\[BOT\]" && pass "labels a bot without exempting it" || fail "bot not labelled"

# ── 4. acknowledgement is the ONLY way to 0, and it is per-comment-id ─────────────────────────
run X=1 -- --number 2 --repo "$FIXTURE_REPO" --acknowledge
[ "$RC" = "0" ] && pass "--acknowledge succeeds" || fail "--acknowledge exited $RC: $OUT"
run X=1 -- --number 2 --repo "$FIXTURE_REPO"
[ "$RC" = "0" ] && pass "the thread PASSES once acknowledged" || fail "post-ack exited $RC: $OUT"

# a NEW comment after the ack re-closes the gate — the ack is bound to ids, not to the thread
fixture "repos/$FIXTURE_REPO/issues/2/comments" \
  '[{"id":9001,"body":"old","created_at":"2026-07-30T10:00:00Z","html_url":"https://x/1","user":{"login":"maintainer","type":"User"}},
    {"id":9003,"body":"NEW reply you have not seen","created_at":"2026-07-31T09:00:00Z","html_url":"https://x/3","user":{"login":"maintainer","type":"User"}}]'
run X=1 -- --number 2 --repo "$FIXTURE_REPO"
[ "$RC" = "1" ] && pass "a NEW comment re-closes the gate despite the prior ack" \
  || fail "new comment exited $RC — the ack must bind to ids, not to the thread"
printf '%s' "$OUT" | grep -q "issue:9003" && pass "only the unacknowledged comment is listed" || fail "wrong listing"
printf '%s' "$OUT" | grep -q "issue:9001" && fail "already-acknowledged comment re-listed" \
  || pass "already-acknowledged comment is not re-listed"

# ── 5. anti-forgery — an ack for one thread cannot authorize another ──────────────────────────
fixture "repos/$FIXTURE_REPO/issues/3" \
  '{"number":3,"title":"a different thread","state":"open"}'
fixture "repos/$FIXTURE_REPO/issues/3/comments" \
  '[{"id":7001,"body":"unrelated","created_at":"2026-07-30T10:00:00Z","html_url":"https://x/9","user":{"login":"someone","type":"User"}}]'
run X=1 -- --number 3 --repo "$FIXTURE_REPO"
[ "$RC" = "1" ] && pass "a different thread is NOT opened by the first thread's ack" \
  || fail "thread #3 exited $RC — acks must be target-bound"

# ── 6. PR-only surfaces: reviews and inline comments count; PENDING does not ───────────────────
fixture "repos/$FIXTURE_REPO/issues/4" \
  '{"number":4,"title":"a pull request","state":"open","pull_request":{"merged_at":"2026-07-31T00:00:00Z"}}'
fixture "repos/$FIXTURE_REPO/pulls/4/reviews" \
  '[{"id":5001,"body":"please change this","state":"CHANGES_REQUESTED","submitted_at":"2026-07-30T12:00:00Z","html_url":"https://x/r1","user":{"login":"reviewer","type":"User"}},
    {"id":5002,"body":"draft thoughts","state":"PENDING","submitted_at":"2026-07-30T13:00:00Z","html_url":"https://x/r2","user":{"login":"reviewer","type":"User"}}]'
fixture "repos/$FIXTURE_REPO/pulls/4/comments" \
  '[{"id":6001,"body":"inline nit","path":"cli/src/limen/io.py","created_at":"2026-07-30T12:30:00Z","html_url":"https://x/c1","user":{"login":"reviewer","type":"User"}}]'
run X=1 -- --number 4 --repo "$FIXTURE_REPO"
[ "$RC" = "1" ] && pass "a PR's reviews and inline comments close the gate" || fail "PR exited $RC: $OUT"
printf '%s' "$OUT" | grep -q "review:5001" && pass "a review body counts as a comment" || fail "review not counted"
printf '%s' "$OUT" | grep -q "CHANGES_REQUESTED" && pass "prints the review state" || fail "review state missing"
printf '%s' "$OUT" | grep -q "reviewcomment:6001" && pass "an inline review comment counts" || fail "inline comment not counted"
printf '%s' "$OUT" | grep -q "review:5002" && fail "a PENDING review (invisible to others) was counted" \
  || pass "a PENDING review is correctly excluded"
printf '%s' "$OUT" | grep -q "already MERGED" \
  && pass "warns that the PR is already merged" || fail "no merged warning"

# ── 7. truncation is REPORTED, never silent (Data Grounding) ───────────────────────────────────
python3 - "$TMP/fixtures" "$FIXTURE_REPO" <<'PY'
import json, os, re, sys
fixtures, repo = sys.argv[1], sys.argv[2]
key = re.sub(r"[^A-Za-z0-9]+", "_", f"repos/{repo}/issues/5/comments").strip("_")
rows = [{"id": 8000 + i, "body": f"c{i}", "created_at": "2026-07-30T10:00:00Z",
         "html_url": "https://x/n", "user": {"login": "u", "type": "User"}} for i in range(100)]
json.dump(rows, open(os.path.join(fixtures, key + ".json"), "w"))
head = re.sub(r"[^A-Za-z0-9]+", "_", f"repos/{repo}/issues/5").strip("_")
json.dump({"number": 5, "title": "big thread", "state": "open"},
          open(os.path.join(fixtures, head + ".json"), "w"))
PY
run GH_NO_SLURP=1 -- --number 5 --repo "$FIXTURE_REPO"
printf '%s' "$OUT" | grep -q "PARTIAL read" \
  && pass "a single-page fallback at the page limit reports a PARTIAL read" \
  || fail "truncation was silent — a gate that passes on what it did not read"

# ── 8. the registry's target pattern refuses cross-repo rather than checking the wrong thread ──
pattern_report="$(python3 - "$REGISTRY" <<'PY'
import re, sys, yaml
spec = yaml.safe_load(open(sys.argv[1]))["effectors"]["github.comment"]
pattern = re.compile(spec["target"]["pattern"])
# Both repo-flag orders, both aliases, a shell-variable number, and — the subtle one — an
# UNRELATED trailing `-R` in a later command that must NOT poison an otherwise-extractable target.
cases = [
    ("gh pr comment 1720 --body hi",                 "1720"),
    ("gh issue comment 320 --body-file x.md",        "320"),
    ("gh pr comment 5 -R other/repo --body x",       None),
    ("gh pr comment 5 --repo other/repo --body x",   None),
    ("gh pr comment --repo other/repo 5 --body x",   None),
    ("gh pr comment -R other/repo 5 --body x",       None),
    ('gh pr comment "$PR" --body x',                 None),
    ("gh pr comment 7 --body x ; gh pr list -R a/b", "7"),
]
bad = []
for command, want in cases:
    match = pattern.search(command)
    got = match.group(1) if match else None
    if got != want:
        bad.append(f"{command!r} want={want!r} got={got!r}")
print("TARGET_PATTERN_OK" if not bad else "TARGET_PATTERN_FAIL: " + " | ".join(bad))
PY
)"
case "$pattern_report" in
  TARGET_PATTERN_OK)
    pass "the target pattern extracts a bare number and refuses every repo-flag form" ;;
  *)
    fail "target pattern would check the AMBIENT repo for a cross-repo comment — $pattern_report" ;;
esac

echo
if [ "$fails" -eq 0 ]; then
  echo "preflight-thread-state: all checks passed"
  exit 0
fi
echo "preflight-thread-state: $fails check(s) FAILED"
exit 1
