#!/usr/bin/env bash
# insights-capture.sh — SessionEnd hook.
# Archives a fresh /insights report.html into the immutable snapshot archive
# (claude-runtime-state) so insights history stops depending on manual runs.
#
# Safe by construction:
#   - no-op if there is no NEW report     (insights-snapshot --only-if-newer)
#   - no-op if the tool isn't deployed yet (feat/insights-diff-rescue unmerged)
#   - never blocks session end             (always exit 0)
# Idempotent: the snapshot dir is stamped by report.html's mtime, so repeated
# runs (incl. concurrent fleet sessions) converge on one snapshot per report.
set -u

REPORT="$HOME/.claude/usage-data/report.html"
LOG="$HOME/.claude/usage-data/.capture.log"

# Locate the tool: prefer the chezmoi-deployed path, else PATH. Silent no-op if
# absent (it ships on the feat/insights-diff-rescue branch, not yet applied).
TOOL="$HOME/.local/bin/insights-snapshot"
if [ ! -x "$TOOL" ]; then
  TOOL="$(command -v insights-snapshot 2>/dev/null || true)"
fi
[ -n "${TOOL:-}" ] && [ -x "$TOOL" ] || exit 0
[ -f "$REPORT" ] || exit 0

# --only-if-newer: exit immediately if this report is already archived.
# --quiet: no output on the common no-op path; only errors hit the log.
"$TOOL" --only-if-newer --quiet 2>>"$LOG" || true
exit 0
