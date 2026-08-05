#!/usr/bin/env bash
# runner-install.sh — register a SELF-HOSTED Actions runner for the organvm org on this Mac.
#
# WHY: the conductor (organvm/limen) went private 2026-07-16, so its CI bills paid minutes —
# 37k min (~$223) in July alone at the hosted rate. A self-hosted runner on the always-on Mac is
# the $0 lane (economic-ground-truth: all exec = $0 capex). Workflows opt in via
#   runs-on: ${{ vars.LIMEN_RUNS_ON || 'ubuntu-latest' }}
# so ONE org/repo Actions variable (LIMEN_RUNS_ON=self-hosted) flips the fleet and unsetting it
# reverts to hosted — no workflow edits either way.
#
# THE SECURITY INVARIANT (non-negotiable): self-hosted runners serve PRIVATE repos ONLY. A public
# repo lets any fork PR execute arbitrary code on this Mac. This script asserts the org's default
# runner group has allows_public_repositories=false and (with --apply) enforces it BEFORE
# registering; never add `self-hosted` labels to a public repo's workflow.
#
# DRY-RUN by default (the consolidate-github.py idiom): prints the full plan and every violated
# precondition. `--apply` performs: group hardening → download → configure → `svc.sh install`
# (generates the launchd LaunchAgent). It NEVER auto-starts the service — host daemon arming is
# deliberate (the gen-launchd-plist discipline): the one printed `svc.sh start` line is the
# operator's (or a post-pause session's) single act.
#
# Env: LIMEN_RUNNER_ORG (organvm), LIMEN_RUNNER_DIR (~/Workspace/_actions-runner),
#      LIMEN_RUNNER_NAME (limen-mac), LIMEN_RUNNER_LABELS (self-hosted,macOS,ARM64)
set -euo pipefail

ORG="${LIMEN_RUNNER_ORG:-organvm}"
DIR="${LIMEN_RUNNER_DIR:-$HOME/Workspace/_actions-runner}"
NAME="${LIMEN_RUNNER_NAME:-limen-mac}"
LABELS="${LIMEN_RUNNER_LABELS:-self-hosted,macOS,ARM64}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

say() { printf '%s\n' "$*"; }
die() { printf 'runner-install: %s\n' "$*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh CLI not found"
command -v curl >/dev/null 2>&1 || die "curl not found"

# ── preflight: token can administer org runners (admin:org) ──────────────────────────────────────
if ! gh api "/orgs/$ORG/actions/runners" --jq .total_count >/dev/null 2>&1; then
  die "cannot read /orgs/$ORG/actions/runners — the gh token needs admin:org (gh auth refresh -h github.com -s admin:org)"
fi

# ── the security invariant: default runner group must refuse public repos ───────────────────────
group_json="$(gh api "/orgs/$ORG/actions/runner-groups" --jq '.runner_groups[] | select(.default)' 2>/dev/null || true)"
[ -n "$group_json" ] || die "no default runner group visible on $ORG"
group_id="$(printf '%s' "$group_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
allows_public="$(printf '%s' "$group_json" | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("allows_public_repositories", True)).lower())')"

if [ "$allows_public" = "true" ]; then
  if [ "$APPLY" = "1" ]; then
    gh api -X PATCH "/orgs/$ORG/actions/runner-groups/$group_id" -F allows_public_repositories=false >/dev/null
    say "✓ hardened: default runner group $group_id now refuses public repositories"
  else
    say "✗ VIOLATION (would fix with --apply): default runner group allows PUBLIC repos — fork-PR code execution risk"
  fi
else
  say "✓ default runner group refuses public repositories"
fi

# ── idempotence: already registered? ────────────────────────────────────────────────────────────
existing="$(gh api "/orgs/$ORG/actions/runners" --jq ".runners[] | select(.name==\"$NAME\") | .status" 2>/dev/null || true)"
if [ -n "$existing" ]; then
  say "✓ runner '$NAME' already registered on $ORG (status: $existing) — nothing to install"
  say "  start/stop: cd $DIR && ./svc.sh start|stop|status"
  exit 0
fi

# ── the plan ────────────────────────────────────────────────────────────────────────────────────
say "plan: register org runner '$NAME' on $ORG"
say "  dir:    $DIR"
say "  labels: $LABELS  (use in PRIVATE-repo workflows only)"
say "  flip:   gh variable set LIMEN_RUNS_ON --org $ORG --body self-hosted   (unset to revert to hosted)"
if [ "$APPLY" != "1" ]; then
  say "DRY-RUN complete — re-run with --apply to download, configure, and install the launchd service (never auto-started)."
  exit 0
fi

# ── download the latest osx-arm64 runner ────────────────────────────────────────────────────────
mkdir -p "$DIR"
cd "$DIR"
url="$(gh api /repos/actions/runner/releases/latest --jq '.assets[].browser_download_url' | grep 'osx-arm64-[0-9].*\.tar\.gz$' | head -1)"
[ -n "$url" ] || die "could not resolve the latest actions-runner osx-arm64 asset"
say "downloading $(basename "$url") …"
curl -fsSL -o runner.tar.gz "$url"
tar xzf runner.tar.gz && rm -f runner.tar.gz

# ── configure against the org (short-lived registration token; never stored) ────────────────────
reg_token="$(gh api -X POST "/orgs/$ORG/actions/runners/registration-token" --jq .token)"
[ -n "$reg_token" ] || die "could not mint a registration token for $ORG"
./config.sh --url "https://github.com/$ORG" --token "$reg_token" --name "$NAME" --labels "$LABELS" --unattended --replace

# ── persistence: install the launchd service, NEVER auto-start (deliberate host arming) ─────────
./svc.sh install
say ""
say "✓ runner '$NAME' configured + launchd service installed (not started)."
say "  ONE remaining act (deliberate host arming):  cd $DIR && ./svc.sh start"
say "  then flip the fleet:  gh variable set LIMEN_RUNS_ON --org $ORG --body self-hosted"
