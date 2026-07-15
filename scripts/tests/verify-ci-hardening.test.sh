#!/usr/bin/env bash
set -euo pipefail

# CI fail-closed contract for scripts/verify.py --changed (issue #1048).
#
# pr-gate runs the resolver as the ONE required check, so a resolver that greens
# without verifying is a fleet-wide hole. These fixtures pin the contract:
#   1. --require-base + unresolvable merge-base  → hard error, never the silent
#      staged/unstaged/untracked fallback (which is EMPTY on a clean CI checkout).
#   2. --require-base + resolved base + empty diff → hard error (a real PR diff
#      is never empty; emptiness means resolution broke).
#   3. Without --require-base the local behavior is unchanged: empty diff exits 0.
#   4. --require-base + deploy-trigger hit → exec the whole matrix via the
#      LIMEN_VERIFY_WHOLE_CMD seam (default scripts/verify-whole.sh).
#   5. --skip-ci-covered JOB → a gate whose ci_job mirror is a DIFFERENT workflow
#      job defers (its own workflow runs on the same PR; merge-policy holds on red),
#      while gates with no mirror or with the running job's mirror still run.
#
# Hermetic: verify.py resolves ROOT from its own location, so copying it into a
# throwaway git repo with a minimal fixture registry sandboxes every run.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fails=0

pass() { printf 'ok %s\n' "$1"; }
flunk() { printf 'FAIL %s\n  %s\n' "$1" "$2"; fails=$((fails + 1)); }

make_sandbox() {
  local dir
  dir="$(mktemp -d "${TMPDIR:-/tmp}/verify-ci-hardening.XXXXXX")"
  mkdir -p "$dir/scripts" "$dir/institutio/governance" "$dir/src" "$dir/web/app" "$dir/webish"
  cp "$ROOT/scripts/verify.py" "$dir/scripts/verify.py"
  cat >"$dir/institutio/governance/gates.yaml" <<'YAML'
schema_version: 0.1
deploy_triggers:
  dashboard:
    workflow: .github/workflows/deploy.yml
    paths: ["web/app/**"]
gates:
  runs-here:
    command: "touch ran-runs-here"
    paths: ["src/**"]
    owner: verify
    note: "fixture gate with no CI mirror — must run in scoped mode"
  own-job:
    command: "touch ran-own-job"
    paths: ["src/**"]
    ci_job: "pr-gate.yml:pr-gate"
    owner: verify
    note: "fixture gate mirrored in the running job — must still run under --skip-ci-covered"
  covered-elsewhere:
    command: "exit 1"
    paths: ["webish/**"]
    ci_job: "ci.yml:web"
    owner: verify
    note: "fixture gate mirrored in another workflow — must defer under --skip-ci-covered, never run"
YAML
  touch "$dir/src/.keep" "$dir/web/app/.keep" "$dir/webish/.keep"
  git -C "$dir" init -q -b main
  git -C "$dir" -c user.email=t@t -c user.name=t add -A
  git -C "$dir" -c user.email=t@t -c user.name=t commit -qm base
  echo "$dir"
}

commit_touch() { # sandbox path — commit a one-file change on top of base
  local dir="$1" path="$2"
  echo x >"$dir/$path"
  git -C "$dir" -c user.email=t@t -c user.name=t add "$path"
  git -C "$dir" -c user.email=t@t -c user.name=t commit -qm "touch $path"
}

# ── 1: unresolvable merge-base fails closed (flag and env forms) ───────────────
sb="$(make_sandbox)"
out="$(python3 "$sb/scripts/verify.py" --changed --base origin/nonexistent --require-base 2>&1)" \
  && flunk require-base-flag "exit 0 despite unresolvable base" \
  || { grep -q "refusing to fail open" <<<"$out" \
         && pass require-base-flag \
         || flunk require-base-flag "missing refusal message: $out"; }
out="$(LIMEN_VERIFY_REQUIRE_BASE=1 python3 "$sb/scripts/verify.py" --changed --base origin/nonexistent 2>&1)" \
  && flunk require-base-env "exit 0 despite unresolvable base (env form)" \
  || pass require-base-env

# ── 2: resolved base + empty diff fails closed ─────────────────────────────────
out="$(python3 "$sb/scripts/verify.py" --changed --base HEAD --require-base 2>&1)" \
  && flunk empty-diff-closed "exit 0 despite empty changed set" \
  || { grep -q "changed set is empty" <<<"$out" \
         && pass empty-diff-closed \
         || flunk empty-diff-closed "missing empty-diff message: $out"; }

# ── 3: local behavior unchanged — empty diff without the flag exits 0 ──────────
out="$(python3 "$sb/scripts/verify.py" --changed --base HEAD 2>&1)" \
  && { grep -q "nothing to verify" <<<"$out" \
         && pass empty-diff-local \
         || flunk empty-diff-local "missing nothing-to-verify message: $out"; } \
  || flunk empty-diff-local "non-zero exit without --require-base: $out"

# ── 4: deploy-trigger diff escalates to the whole matrix (seam) ────────────────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" web/app/page.txt
printf '#!/usr/bin/env bash\ntouch "%s/whole-ran"\n' "$sb" >"$sb/whole-marker.sh"
out="$(LIMEN_VERIFY_WHOLE_CMD="$sb/whole-marker.sh" \
       python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  || flunk deploy-escalation "escalated run exited non-zero: $out"
[[ -f "$sb/whole-ran" ]] \
  && pass deploy-escalation \
  || flunk deploy-escalation "LIMEN_VERIFY_WHOLE_CMD marker never ran: $out"
rm -f "$sb/whole-ran"
out="$(LIMEN_VERIFY_WHOLE_CMD="$sb/whole-marker.sh" \
       python3 "$sb/scripts/verify.py" --changed --base "$base_sha" 2>&1)" \
  || flunk deploy-no-escalation-local "local run exited non-zero: $out"
[[ ! -f "$sb/whole-ran" ]] \
  && pass deploy-no-escalation-local \
  || flunk deploy-no-escalation-local "escalated without --require-base"

# ── 5: --skip-ci-covered defers foreign-job mirrors, runs everything else ──────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" webish/x.txt
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk covered-runs-by-default "covered-elsewhere (exit 1) did not run without the flag" \
  || pass covered-runs-by-default
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base \
       --skip-ci-covered pr-gate.yml:pr-gate 2>&1)" \
  || flunk skip-ci-covered "deferral run exited non-zero: $out"
grep -q "deferred: covered-elsewhere (covered by ci.yml:web)" <<<"$out" \
  && pass skip-ci-covered \
  || flunk skip-ci-covered "missing deferred line: $out"

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" src/a.txt
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base \
       --skip-ci-covered pr-gate.yml:pr-gate 2>&1)" \
  || flunk own-job-still-runs "run exited non-zero: $out"
[[ -f "$sb/ran-runs-here" && -f "$sb/ran-own-job" ]] \
  && pass own-job-still-runs \
  || flunk own-job-still-runs "unmirrored/own-job gates were skipped: $out"

if ((fails)); then
  printf '\nverify-ci-hardening: %d case(s) FAILED\n' "$fails"
  exit 1
fi
printf '\nverify-ci-hardening: all fail-closed fixtures pass\n'
