import sys
with open('/tmp/atlas_worktree/scripts/heartbeat-loop.sh', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if 'C_EVOCATOR="${LIMEN_BEAT_EVOCATOR:-6}"' in line:
        new_lines.extend([
            "C_ATLAS=\"${LIMEN_BEAT_ATLAS:-6}\"         # ATLAS (the complete map of all repos across organvm and 4444J99)\n"
        ])
    new_lines.append(line)

with open('/tmp/atlas_worktree/scripts/heartbeat-loop.sh', 'w') as f:
    f.writelines(new_lines)

