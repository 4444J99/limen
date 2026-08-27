#!/usr/bin/env bash
# Compatibility circuit breaker for the retired synchronous PR waiter.
#
# Waiting belongs to GitHub's merge queue and Limen's recurring merge drain, not to an agent or
# provider process. This path remains executable so stale instructions fail immediately instead
# of recreating the multi-day re-arm loop.
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "await-pr.sh is retired; synchronous PR waits are forbidden."
  echo "Submit one exact head once:"
  echo "  scripts/merge-drain.py --repo OWNER/NAME --pr NUMBER --expected-head SHA"
  exit 0
fi

echo "AWAIT-PR: REFUSED — synchronous PR waiters are retired." >&2
echo "Use one exact-head submission and return control:" >&2
echo "  scripts/merge-drain.py --repo OWNER/NAME --pr NUMBER --expected-head SHA" >&2
echo "GitHub plus the recurring merge drain own later observation; never retry or poll." >&2
exit 64
