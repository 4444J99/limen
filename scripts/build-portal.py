#!/usr/bin/env python3
"""
Build the front-door portal into the 200+ repo estate (VLTA/PORTUS).
It uses the repo-surface-ledger data to generate a single navigable entry point.
"""

import os
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)).resolve()
LEDGER_DOC = ROOT / "docs" / "repo-surface-ledger.md"
PORTAL_DIR = ROOT / "public-portal"

def parse_ledger_doc(doc_text: str) -> dict:
    repos = []
    
    in_repos_table = False
    for line in doc_text.splitlines():
        if "## Repo Surfaces" in line:
            in_repos_table = True
            continue
        
        if in_repos_table and line.startswith("| `"):
            # | `repo` | `branch` | dirty | `remote` | products | tests | deploys | visibility | location | remote class | disposition | gate |
            parts = [p.strip().strip("`") for p in line.split("|")[1:-1]]
            if len(parts) >= 12:
                repos.append({
                    "path_label": parts[0],
                    "branch": parts[1],
                    "remote_hash": parts[3],
                    "visibility_state": parts[7],
                    "classification": {
                        "location": parts[8],
                        "remote": parts[9],
                        "disposition": parts[10],
                    }
                })
    
    return {"repos": repos, "repo_count": len(repos), "generated_at": "extracted from ledger"}

def build_html(data: dict) -> str:
    repos = data.get("repos", [])
    
    # Group by location, then disposition
    grouped = {}
    for repo in repos:
        loc = repo.get("classification", {}).get("location", "unclassified")
        disp = repo.get("classification", {}).get("disposition", "unclassified")
        grouped.setdefault(loc, {}).setdefault(disp, []).append(repo)

    html = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "    <meta charset='UTF-8'>",
        "    <title>VLTA / PORTUS - The Front Door</title>",
        "    <style>",
        "        body { font-family: system-ui, sans-serif; line-height: 1.6; max-width: 1200px; margin: 0 auto; padding: 2rem; background-color: #f9f9f9; }",
        "        h1, h2, h3 { color: #222; }",
        "        .repo-card { background: white; border: 1px solid #ddd; padding: 1rem; margin-bottom: 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }",
        "        .tag { display: inline-block; padding: 0.2rem 0.6rem; background: #eee; border-radius: 4px; font-size: 0.8rem; margin-right: 0.5rem; color: #555; }",
        "        .tag.public { background: #e6f3ff; color: #0066cc; }",
        "        .tag.remote { background: #e6ffe6; color: #006600; }",
        "        a { color: #0066cc; text-decoration: none; }",
        "        a:hover { text-decoration: underline; }",
        "    </style>",
        "</head>",
        "<body>",
        "    <h1>VLTA / PORTUS</h1>",
        "    <p>The single navigable front door into the civilizational estate.</p>",
        f"    <p><em>Generated from {data.get('repo_count', 0)} repos (from repo-surface-ledger)</em></p>",
    ]

    for loc in sorted(grouped.keys()):
        html.append(f"    <h2>Location: {loc}</h2>")
        for disp in sorted(grouped[loc].keys()):
            html.append(f"    <h3>Disposition: {disp}</h3>")
            for repo in sorted(grouped[loc][disp], key=lambda x: x.get("path_label", "")):
                name = repo.get("path_label", "unknown")
                branch = repo.get("branch", "unknown")
                remote = repo.get("remote_hash", "none")
                vis = repo.get("visibility_state", "unknown")
                
                # Link resolving logic
                if name.startswith("~/Workspace/"):
                    repo_name = name.split("/")[-1]
                else:
                    repo_name = name
                link = f"https://github.com/organvm/{repo_name}"
                
                html.append("    <div class='repo-card'>")
                html.append(f"        <strong><a href='{link}'>{name}</a></strong>")
                html.append("        <div style='margin-top: 0.5rem;'>")
                html.append(f"            <span class='tag'>branch: {branch}</span>")
                html.append(f"            <span class='tag'>remote: {remote}</span>")
                html.append(f"            <span class='tag'>vis: {vis}</span>")
                html.append("        </div>")
                html.append("    </div>")
    
    html.extend([
        "</body>",
        "</html>"
    ])
    
    return "\n".join(html)

def main():
    PORTAL_DIR.mkdir(exist_ok=True)
    
    if not LEDGER_DOC.exists():
        print(f"Error: Ledger doc {LEDGER_DOC} not found. Run scripts/repo-surface-ledger.py --write first.")
        return 1
        
    doc_text = LEDGER_DOC.read_text(encoding="utf-8")
    data = parse_ledger_doc(doc_text)
    
    html_content = build_html(data)
    
    index_path = PORTAL_DIR / "index.html"
    index_path.write_text(html_content, encoding="utf-8")
    
    readme_path = PORTAL_DIR / "README.md"
    readme_path.write_text(f"# VLTA / PORTUS\n\nGenerated portal for {data.get('repo_count', 0)} repos.\nSee `index.html` for the full view.\n", encoding="utf-8")
    
    print(f"Portal built successfully at {PORTAL_DIR} with {data.get('repo_count', 0)} repos.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
