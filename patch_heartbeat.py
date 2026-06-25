import re

with open("/tmp/worktrees/feat-integrity/scripts/heartbeat-loop.sh", "r") as f:
    content = f.read()

# I want to insert it AFTER `play "$C_WEB"     && bash "$LIMEN_ROOT/scripts/refresh-web.sh" >>"$LIMEN_ROOT/logs/refresh-web.log" 2>&1 || true`
# and BEFORE `# QUICKEN`

integrity_block = """
  # INTEGRITY — govern the autoupdater + verify signatures (CISO)
  python3 "$LIMEN_ROOT/cli/src/limen/__main__.py" integrity >> "$LIMEN_ROOT/logs/integrity.log" 2>&1 || true
"""

insert_idx = content.find('  # QUICKEN — a session has a lifecycle')
if insert_idx != -1:
    content = content[:insert_idx] + integrity_block + "\n" + content[insert_idx:]
    with open("/tmp/worktrees/feat-integrity/scripts/heartbeat-loop.sh", "w") as f:
        f.write(content)
    print("Patched heartbeat-loop.sh")
else:
    print("Could not find insert location")
