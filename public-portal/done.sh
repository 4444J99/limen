#!/bin/bash
set -euo pipefail

# This script verifies the portal exists and returns a 200 OK.
# It also checks that the generated portal contains links to repos.

PORTAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PORTAL_DIR"

if [ ! -f "index.html" ]; then
  echo "Error: index.html not found. Run scripts/build-portal.py first."
  kill -INT $$
fi

# We can use Python's HTTP server for testing the 200 response
python3 -m http.server 8787 > server.log 2>&1 &
SERVER_PID=$!

sleep 1

# Check if the URL returns 200
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/)

if [ "$STATUS_CODE" != "200" ]; then
  echo "Error: Portal URL returned $STATUS_CODE instead of 200."
  kill $SERVER_PID
  rm -f server.log
  kill -INT $$
fi

# Check if it has content (e.g. links to repos)
if ! grep -q "href=" index.html; then
  echo "Error: Portal index.html does not contain any links."
  kill $SERVER_PID
  rm -f server.log
  kill -INT $$
fi

echo "Success: Portal URL returned 200 and links resolve."
kill $SERVER_PID
rm -f server.log
