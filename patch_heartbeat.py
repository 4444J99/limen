import sys
with open('/tmp/atlas_worktree/scripts/heartbeat-loop.sh', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if '# EVOCATOR — the SVMMONER' in line:
        new_lines.extend([
            "  # ATLAS — the COMPLETE map of all repos across organvm and 4444J99.\n",
            "  # Renders the full universe to institutio/registry/atlas.json so the operator has\n",
            "  # a complete live registry. This NEVER replaces value-repos.json (which is the fail-closed\n",
            "  # token-spending tier). Idempotent (no diff if nothing changed). Bounded + fail-open.\n",
            "  play \"$C_ATLAS\" && python3 \"$LIMEN_ROOT/scripts/generate-atlas.py\" 2>&1 | tail -2 || true\n",
            "\n"
        ])
    new_lines.append(line)

with open('/tmp/atlas_worktree/scripts/heartbeat-loop.sh', 'w') as f:
    f.writelines(new_lines)

