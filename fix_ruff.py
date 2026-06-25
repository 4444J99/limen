with open("/tmp/worktrees/feat-integrity/cli/src/limen/cli.py", "r") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if line.strip() == "from limen.integrity import check_integrity":
        lines[i] = ""
    elif "from limen.io import load_limen_file" in line:
        lines[i] = "from limen.io import load_limen_file\nfrom limen.integrity import check_integrity\n"

with open("/tmp/worktrees/feat-integrity/cli/src/limen/cli.py", "w") as f:
    f.write("".join(lines))


with open("/tmp/worktrees/feat-integrity/cli/src/limen/integrity.py", "r") as f:
    lines = f.readlines()
with open("/tmp/worktrees/feat-integrity/cli/src/limen/integrity.py", "w") as f:
    for line in lines:
        if "expected_autoupdater_state" not in line:
            f.write(line)

with open("/tmp/worktrees/feat-integrity/cli/tests/test_integrity.py", "r") as f:
    lines = f.readlines()
with open("/tmp/worktrees/feat-integrity/cli/tests/test_integrity.py", "w") as f:
    for line in lines:
        if "import subprocess" not in line:
            f.write(line)
