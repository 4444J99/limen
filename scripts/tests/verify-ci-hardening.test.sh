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
#   5. --integration + deploy-trigger hit → require an explicit base that is an
#      ancestor of HEAD and its exact merge-base, then run implicated gates
#      without repeating the immutable PR-head whole matrix.
#   6. --skip-ci-covered JOB → a gate whose ci_job mirror is a DIFFERENT workflow
#      job defers (its own workflow runs on the same PR; merge-policy holds on red),
#      while gates with no mirror or with the running job's mirror still run.
#   7. LIMEN_VERIFY_NO_DEPLOY_ESCALATION=1 + --require-base + deploy-trigger hit →
#      stays scoped (never execs the whole matrix), prints the suppression receipt,
#      and still ends with the website-sensitive NOTE (merge-policy owns the full
#      matrix pre-merge). The default (env unset) keeps escalating — fixture 4.
#
# Hermetic: verify.py resolves ROOT from its own location, so copying it into a
# throwaway git repo with a minimal fixture registry sandboxes every run.
#
# Hermetic in ENV too: pr-gate's PR step exports the verify-family env (REQUIRE_BASE,
# NO_DEPLOY_ESCALATION, NO_LOCK) for its own scoped run, and this test runs INSIDE
# that step whenever verify.py changes — ambient values would silently flip what a
# fixture exercises (fixture 4 escalates only when NO_DEPLOY_ESCALATION is unset).
# Each fixture sets exactly the env it tests; everything ambient is stripped here.

unset LIMEN_VERIFY_REQUIRE_BASE LIMEN_VERIFY_NO_DEPLOY_ESCALATION \
  LIMEN_VERIFY_WHOLE_CMD LIMEN_VERIFY_NO_LOCK LIMEN_VERIFY_LOCK_FILE

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fails=0

pass() { printf 'ok %s\n' "$1"; }
flunk() { printf 'FAIL %s\n  %s\n' "$1" "$2"; fails=$((fails + 1)); }

make_sandbox() {
  local dir
  dir="$(mktemp -d "${TMPDIR:-/tmp}/verify-ci-hardening.XXXXXX")"
  mkdir -p "$dir/scripts" "$dir/institutio/governance" "$dir/institutio/vault" "$dir/docs/keys" "$dir/src" "$dir/web/app" "$dir/webish"
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
  deleted-custody:
    command: "touch ran-deleted-custody"
    paths: ["institutio/vault/**", "docs/keys/anthony-padavano-gpg.asc", ".limen-private", ".limen-private/**", ".agent-runtime", ".agent-runtime/**", ".limen-workstream", ".limen-workstream/**"]
    owner: custody
    note: "deleted custody paths must remain eligible for scoped gate selection"
YAML
  touch "$dir/src/.keep" "$dir/institutio/vault/artifact.gpg" "$dir/docs/keys/anthony-padavano-gpg.asc" "$dir/web/app/.keep" "$dir/webish/.keep"
  git -C "$dir" init -q -b main
  git -C "$dir" -c user.email=t@t -c user.name=t add -A
  git -C "$dir" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm base
  echo "$dir"
}

commit_touch() { # sandbox path — commit a one-file change on top of base
  local dir="$1" path="$2"
  echo x >"$dir/$path"
  git -C "$dir" -c user.email=t@t -c user.name=t add "$path"
  git -C "$dir" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "touch $path"
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

# ── 4: deleting every custody file still selects its scoped gate ──────────────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
rm "$sb/institutio/vault/artifact.gpg"
git -C "$sb" -c user.email=t@t -c user.name=t add -u institutio/vault/artifact.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "delete custody"
out_file="$sb/verify.out"
if python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base >"$out_file" 2>&1
then
  :
else
  out="$(<"$out_file")"
  flunk deleted-path-selects-gate "deleted-path run exited non-zero: $out"
fi
if [[ -f "$sb/ran-deleted-custody" ]]
then
  pass deleted-path-selects-gate
else
  out="$(<"$out_file")"
  flunk deleted-path-selects-gate "deleted custody path was filtered out: $out"
fi

# ── 4a: renaming every custody file still selects its scoped gate ────────────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
mkdir "$sb/elsewhere"
git -C "$sb" mv institutio/vault/artifact.gpg elsewhere/artifact.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "rename custody away"
out_file="$sb/verify.out"
if python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base >"$out_file" 2>&1
then
  :
else
  out="$(<"$out_file")"
  flunk renamed-path-selects-gate "renamed-path run exited non-zero: $out"
fi
if [[ -f "$sb/ran-deleted-custody" ]]
then
  pass renamed-path-selects-gate
else
  out="$(<"$out_file")"
  flunk renamed-path-selects-gate "renamed custody source path was filtered out: $out"
fi

# ── 4b: every private namespace selects the custody gate ─────────────────────
for private_path in \
  ".limen-private" \
  ".limen-private/probe" \
  ".limen-private/résumé.md" \
  ".agent-runtime" \
  ".agent-runtime/probe" \
  ".limen-workstream" \
  ".limen-workstream/probe"
do
  sb="$(make_sandbox)"
  base_sha="$(git -C "$sb" rev-parse HEAD)"
  mkdir -p "$(dirname "$sb/$private_path")"
  printf 'private\n' >"$sb/$private_path"
  git -C "$sb" -c user.email=t@t -c user.name=t add -f "$private_path"
  git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "add private namespace"
  out_file="$sb/verify.out"
  if python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base >"$out_file" 2>&1
  then
    :
  else
    out="$(<"$out_file")"
    flunk private-namespace-selects-gate "private namespace run exited non-zero: $out"
  fi
  if [[ -f "$sb/ran-deleted-custody" ]]
  then
    pass "private-namespace-selects-gate:$private_path"
  else
    flunk private-namespace-selects-gate "private namespace did not select custody gate: $private_path"
  fi
done

# ── 4bc: one final public custody version is eligible for vault validation ─────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
printf 'ciphertext\n' >"$sb/institutio/vault/artifact-new.gpg"
git -C "$sb" -c user.email=t@t -c user.name=t add institutio/vault/artifact-new.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "add final custody version"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  || flunk final-custody-version "single final custody version exited non-zero: $out"
[[ -f "$sb/ran-deleted-custody" ]] \
  && pass final-custody-version \
  || flunk final-custody-version "single final custody version did not select its gate: $out"

# ── 4c: add-then-delete private content is rejected without naming it ─────────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
mkdir -p "$sb/.limen-private"
printf 'private\n' >"$sb/.limen-private/sensitive-probe"
git -C "$sb" -c user.email=t@t -c user.name=t add -f .limen-private/sensitive-probe
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "add transient private content"
git -C "$sb" rm -q .limen-private/sensitive-probe
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "delete transient private content"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk transient-private-history "exit 0 despite committed transient private content" \
  || { grep -q "refusing to expose or certify transient private content" <<<"$out" \
         && ! grep -q "sensitive-probe" <<<"$out" \
         && pass transient-private-history \
         || flunk transient-private-history "missing neutral refusal or leaked path: $out"; }

# ── 4d: historical-only custody names fail without log leakage ────────────────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
printf 'ciphertext\n' >"$sb/institutio/vault/sensitive-probe.gpg"
git -C "$sb" -c user.email=t@t -c user.name=t add institutio/vault/sensitive-probe.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "add transient custody path"
git -C "$sb" rm -q institutio/vault/sensitive-probe.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "delete transient custody path"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk historical-custody-redaction "exit 0 despite deleted transient custody" \
  || { grep -q "refusing to certify an unvalidated intermediate version" <<<"$out" \
         && ! grep -q "sensitive-probe" <<<"$out" \
         && pass historical-custody-redaction \
         || flunk historical-custody-redaction "missing neutral refusal or leaked path: $out"; }

# ── 4e: reverted versions of tracked custody files fail without path leakage ──
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
printf 'transient bytes\n' >>"$sb/institutio/vault/artifact.gpg"
git -C "$sb" -c user.email=t@t -c user.name=t add institutio/vault/artifact.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "mutate tracked custody"
git -C "$sb" restore --source "$base_sha" -- institutio/vault/artifact.gpg
git -C "$sb" -c user.email=t@t -c user.name=t add institutio/vault/artifact.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "restore tracked custody"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk transient-custody-reversion "exit 0 despite an unvalidated intermediate custody version" \
  || { grep -q "refusing to certify an unvalidated intermediate version" <<<"$out" \
         && ! grep -q "artifact.gpg" <<<"$out" \
         && pass transient-custody-reversion \
         || flunk transient-custody-reversion "missing neutral refusal or leaked path: $out"; }

# ── 4e1: superseded custody versions fail even when the final path changed ─────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
printf 'first version\n' >"$sb/institutio/vault/artifact.gpg"
git -C "$sb" -c user.email=t@t -c user.name=t add institutio/vault/artifact.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "first custody version"
printf 'final version\n' >"$sb/institutio/vault/artifact.gpg"
git -C "$sb" -c user.email=t@t -c user.name=t add institutio/vault/artifact.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "supersede custody version"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk superseded-custody-version "exit 0 despite an unvalidated superseded custody version" \
  || { grep -q "refusing to certify an unvalidated intermediate version" <<<"$out" \
         && ! grep -q "artifact.gpg" <<<"$out" \
         && pass superseded-custody-version \
         || flunk superseded-custody-version "missing neutral refusal or leaked path: $out"; }

# ── 4e2: reverted public-key versions receive the same neutral refusal ─────────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
printf 'transient key bytes\n' >>"$sb/docs/keys/anthony-padavano-gpg.asc"
git -C "$sb" -c user.email=t@t -c user.name=t add docs/keys/anthony-padavano-gpg.asc
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "mutate public key"
git -C "$sb" restore --source "$base_sha" -- docs/keys/anthony-padavano-gpg.asc
git -C "$sb" -c user.email=t@t -c user.name=t add docs/keys/anthony-padavano-gpg.asc
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "restore public key"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk transient-public-key "exit 0 despite an unvalidated intermediate public-key version" \
  || { grep -q "refusing to certify an unvalidated intermediate version" <<<"$out" \
         && ! grep -q "anthony-padavano" <<<"$out" \
         && pass transient-public-key \
         || flunk transient-public-key "missing neutral refusal or leaked path: $out"; }

# ── 4ea: add-then-delete public custody files fail without path leakage ────────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
printf 'transient bytes\n' >"$sb/institutio/vault/résumé-cipher.gpg"
git -C "$sb" -c user.email=t@t -c user.name=t add institutio/vault/résumé-cipher.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "add transient custody blob"
git -C "$sb" rm -q institutio/vault/résumé-cipher.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "delete transient custody blob"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk deleted-transient-custody "exit 0 despite a deleted transient custody blob" \
  || { grep -q "refusing to certify an unvalidated intermediate version" <<<"$out" \
         && ! grep -q "résumé-cipher" <<<"$out" \
         && pass deleted-transient-custody \
         || flunk deleted-transient-custody "missing neutral refusal or leaked path: $out"; }

# ── 4f: synthetic merge inventory excludes paths changed only on the base ──────
sb="$(make_sandbox)"
git -C "$sb" switch -q -c feature
commit_touch "$sb" src/feature.txt
git -C "$sb" switch -q main
commit_touch "$sb" webish/base-only.txt
base_sha="$(git -C "$sb" rev-parse HEAD)"
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false merge -q --no-ff feature -m "synthetic PR merge"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  || flunk merge-base-path-exclusion "synthetic merge run exited non-zero: $out"
[[ -f "$sb/ran-runs-here" ]] \
  && ! grep -q "base-only" <<<"$out" \
  && pass merge-base-path-exclusion \
  || flunk merge-base-path-exclusion "feature gate missing or base-only path leaked into scope: $out"

# ── 4g: merge-resolution-only private content remains in the inventory ─────────
sb="$(make_sandbox)"
git -C "$sb" switch -q -c feature
commit_touch "$sb" src/feature.txt
git -C "$sb" switch -q main
commit_touch "$sb" webish/base-only.txt
base_sha="$(git -C "$sb" rev-parse HEAD)"
git -C "$sb" switch -q feature
git -C "$sb" -c user.email=t@t -c user.name=t merge -q --no-ff --no-commit main
mkdir -p "$sb/.limen-private"
printf 'private\n' >"$sb/.limen-private/merge-only-probe"
git -C "$sb" -c user.email=t@t -c user.name=t add -f .limen-private/merge-only-probe
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "merge with private resolution"
git -C "$sb" rm -q .limen-private/merge-only-probe
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "delete merge-only private content"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk merge-resolution-private "exit 0 despite merge-created private history" \
  || { grep -q "refusing to expose or certify transient private content" <<<"$out" \
         && ! grep -q "merge-only-probe" <<<"$out" \
         && pass merge-resolution-private \
         || flunk merge-resolution-private "missing neutral refusal or leaked path: $out"; }

# ── 4h: merge-resolution-only public custody content is also rejected ──────────
sb="$(make_sandbox)"
git -C "$sb" switch -q -c feature
commit_touch "$sb" src/feature.txt
git -C "$sb" switch -q main
commit_touch "$sb" webish/base-only.txt
base_sha="$(git -C "$sb" rev-parse HEAD)"
git -C "$sb" switch -q feature
git -C "$sb" -c user.email=t@t -c user.name=t merge -q --no-ff --no-commit main
printf 'ciphertext\n' >"$sb/institutio/vault/merge-only-cipher.gpg"
git -C "$sb" -c user.email=t@t -c user.name=t add institutio/vault/merge-only-cipher.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "merge with custody resolution"
git -C "$sb" rm -q institutio/vault/merge-only-cipher.gpg
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "delete merge-only custody content"
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  && flunk merge-resolution-custody "exit 0 despite merge-created custody history" \
  || { grep -q "refusing to certify an unvalidated intermediate version" <<<"$out" \
         && ! grep -q "merge-only-cipher" <<<"$out" \
         && pass merge-resolution-custody \
         || flunk merge-resolution-custody "missing neutral refusal or leaked path: $out"; }

# ── 5: deploy-trigger diff escalates to the whole matrix (seam) ────────────────
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

# ── 6: queue integration reuses head matrix and runs scoped composition ────────
rm -f "$sb/whole-ran"
out="$(LIMEN_VERIFY_WHOLE_CMD="$sb/whole-marker.sh" \
       python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --integration 2>&1)" \
  || flunk integration-scoped "integration run exited non-zero: $out"
[[ ! -f "$sb/whole-ran" ]] \
  && grep -q "INTEGRATION: deploy-trigger paths were composed" <<<"$out" \
  && pass integration-scoped \
  || flunk integration-scoped "whole matrix ran or receipt missing: $out"

out="$(python3 "$sb/scripts/verify.py" --changed --base origin/nonexistent --integration 2>&1)" \
  && flunk integration-requires-base "exit 0 despite unresolvable integration base" \
  || pass integration-requires-base

out="$(python3 "$sb/scripts/verify.py" --changed --integration 2>&1)" \
  && flunk integration-requires-explicit-base "exit 0 without an explicit integration base" \
  || { grep -q "no --base was supplied" <<<"$out" \
         && pass integration-requires-explicit-base \
         || flunk integration-requires-explicit-base "missing explicit-base refusal: $out"; }

# A resolvable commit from a sibling history has a common ancestor with HEAD,
# but it is not the queue base of this synthetic merge-group tree.
git -C "$sb" switch -qc competing-base "$base_sha"
echo x >"$sb/src/competing.txt"
git -C "$sb" -c user.email=t@t -c user.name=t add src/competing.txt
git -C "$sb" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "competing base"
competing_sha="$(git -C "$sb" rev-parse HEAD)"
git -C "$sb" switch -q main
out="$(python3 "$sb/scripts/verify.py" --changed --base "$competing_sha" --integration 2>&1)" \
  && flunk integration-rejects-common-ancestor \
       "exit 0 when supplied base was replaced by an older common ancestor" \
  || { grep -q "exact merge-base" <<<"$out" \
         && pass integration-rejects-common-ancestor \
         || flunk integration-rejects-common-ancestor "missing exact-base refusal: $out"; }

# ── 7: --skip-ci-covered defers foreign-job mirrors, runs everything else ──────
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

# ── 8: PR-lane opt-out — deploy diff stays scoped, never execs the matrix ──────
sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" web/app/page.txt
printf '#!/usr/bin/env bash\ntouch "%s/whole-ran"\n' "$sb" >"$sb/whole-marker.sh"
out="$(LIMEN_VERIFY_WHOLE_CMD="$sb/whole-marker.sh" LIMEN_VERIFY_NO_DEPLOY_ESCALATION=1 \
       python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base 2>&1)" \
  || flunk no-escalation-optout "suppressed run exited non-zero: $out"
[[ ! -f "$sb/whole-ran" ]] \
  && grep -q "escalation suppressed" <<<"$out" \
  && grep -q "website-sensitive" <<<"$out" \
  && pass no-escalation-optout \
  || flunk no-escalation-optout "whole matrix ran or suppression receipt missing: $out"

if ((fails)); then
  printf '\nverify-ci-hardening: %d case(s) FAILED\n' "$fails"
  exit 1
fi
printf '\nverify-ci-hardening: all fail-closed fixtures pass\n'
