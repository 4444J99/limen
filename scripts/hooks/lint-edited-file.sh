#!/usr/bin/env bash
# PostToolUse hook: advisory ruff lint of the single file Claude just edited.
#
# Ideal-form evolution of the suggested `npm run lint --silent || true`:
#   - uses this repo's real linter (ruff), not npm (this is a Python-first repo);
#   - scoped to the edited file, so it is fast and quiet (not a whole-repo lint);
#   - Python-only — non-.py edits are a no-op;
#   - ALWAYS exits 0 (advisory) so it never blocks an edit, stalls a lane, or
#     trips the live fleet. It surfaces findings; it does not gate.
#
# Input: PostToolUse hook payload as JSON on stdin (contains tool_input.file_path).
set -u

payload="$(cat)"

file="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
ti = d.get("tool_input", {}) or {}
print(ti.get("file_path") or ti.get("path") or "")
' 2>/dev/null)"

case "$file" in
  *.py) ;;          # only lint Python
  *) exit 0 ;;
esac

[ -f "$file" ] || exit 0

# An explicitly-passed path is linted even if it lives under an excluded dir
# (e.g. a worktree), which is exactly what we want for the just-edited file.
python3 -m ruff check --quiet "$file" 2>&1 || true
exit 0
