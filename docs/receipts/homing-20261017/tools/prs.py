import json
import re
import subprocess
import sys

d = json.load(open(sys.argv[1]))
out = []
for r in d["repos"]:
    if not r.get("pushed"):
        continue
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", r.get("remote", ""))
    slug = m.group(1) if m else None
    for b in r["pushed"]:
        name = b["branch"]
        state = "no-slug"
        prs = []
        if slug:
            q = subprocess.run(
                ["gh", "pr", "list", "--repo", slug, "--head", name, "--state", "all", "--json", "number,state,mergedAt", "--limit", "5"],
                capture_output=True, text=True, timeout=60,
            )
            try:
                prs = json.loads(q.stdout or "[]")
            except ValueError:
                prs = []
            state = "merged" if any(p["state"] == "MERGED" for p in prs) else ("open" if any(p["state"] == "OPEN" for p in prs) else ("closed" if prs else "no-pr"))
        out.append({"repo": r["repo"], "slug": slug, "branch": name, "sha": b["sha"], "pr_state": state, "prs": [p["number"] for p in prs]})
        print(json.dumps(out[-1]))
json.dump(out, open(sys.argv[2], "w"), indent=2)
