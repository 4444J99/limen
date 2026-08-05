#!/usr/bin/env python3
"""
publish-constellation — put the constellation surfaces on Cloudflare Pages.

The atlas and streams generators emit BODY FRAGMENTS: no doctype, no charset,
no viewport. That is deliberate — the Artifact host supplies its own document
shell. A page served from Pages has no such host, and a fragment without a
viewport meta renders desktop-width on a phone, which is precisely how a link
gets opened when it is shown to somebody.

So this tool owns the document shell, and nothing else does:

  1. render the PUBLIC-SAFE half of both surfaces (never the private overlay,
     never private repository names)
  2. wrap each fragment in a real HTML document — charset, viewport, title,
     and `robots: noindex`
  3. add a nav strip so the two surfaces link to each other and to an index
  4. deploy the directory to Cloudflare Pages via wrangler

`robots: noindex` is deliberate. These pages name real people by first name;
the register's public half is built to be shareable, not to be crawled and
ranked. The link works for anyone who has it — it just does not enter search
results. Pass --indexable to opt out of that.

The private atlas is structurally unreachable from here: this tool only ever
invokes the generators in their public modes, and it refuses to publish if a
rendered page still contains a private repository name.

Usage:
  organs/consulting/constellation/publish-constellation.py --dry-run
  organs/consulting/constellation/publish-constellation.py
  organs/consulting/constellation/publish-constellation.py --project my-name
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
ATLAS = HERE / "constellation-atlas.py"
STREAMS = HERE / "constellation-streams.py"
STYLESHEET = HERE / "atlas.css"
CENSUS = REPO_ROOT / "logs" / "constellation" / "estate-census.json"
DIST = REPO_ROOT / "logs" / "constellation" / "dist"
ENV_FILE = Path.home() / ".limen.env"

PROJECT = "constellation"

NAV_CSS = """
.nav {
  display: flex; flex-wrap: wrap; gap: 2px; align-items: center;
  border: 1px solid var(--rule); border-radius: 3px; overflow: hidden;
  background: var(--rule); margin-bottom: 4px;
}
.nav a {
  flex: 1 1 auto; text-align: center; background: var(--surface);
  padding: 9px 14px; text-decoration: none; color: var(--ink-muted);
  font-family: var(--mono); font-size: 11px; letter-spacing: .09em;
  text-transform: uppercase; transition: color .12s ease, background .12s ease;
}
.nav a:hover { color: var(--ink); }
.nav a[aria-current="page"] { color: var(--accent); font-weight: 600; }
.nav a:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
@media (prefers-reduced-motion: reduce) { .nav a { transition: none; } }
"""

INDEX_CSS = """
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
.card {
  display: flex; flex-direction: column; gap: 8px; text-decoration: none;
  background: var(--surface); border: 1px solid var(--rule);
  border-left: 3px solid var(--accent); border-radius: 3px;
  padding: 18px 20px; box-shadow: var(--shadow); color: inherit;
}
.card:hover { border-color: var(--accent); }
.card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.card h2 { font-family: var(--display); font-size: 22px; font-weight: 600; margin: 0; }
.card p { font-size: 13.5px; color: var(--ink-muted); line-height: 1.5; }
.card .go {
  font-family: var(--mono); font-size: 10.5px; letter-spacing: .09em;
  text-transform: uppercase; color: var(--accent); margin-top: auto;
}
.card .stat {
  font-family: var(--mono); font-size: 11px; color: var(--ink-faint);
  font-variant-numeric: tabular-nums;
}
"""

PAGES = [
    ("index.html", "Overview"),
    ("atlas.html", "Atlas"),
    ("streams.html", "Streams"),
]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def _nav(current: str) -> str:
    parts = []
    for href, label in PAGES:
        mark = ' aria-current="page"' if href == current else ""
        parts.append(f'<a href="/{href}"{mark}>{html.escape(label)}</a>')
    return f'<nav class="nav">{"".join(parts)}</nav>'


def document(fragment: str, *, current: str, indexable: bool) -> str:
    """Wrap a generator fragment in a real, mobile-correct HTML document."""
    title_match = re.search(r"<title>(.*?)</title>", fragment, re.DOTALL)
    title = title_match.group(1).strip() if title_match else "The Collaborator Constellation"
    body = re.sub(r"<title>.*?</title>\s*", "", fragment, count=1, flags=re.DOTALL)

    # Nav goes inside the sheet so it inherits the page's own column width.
    body = body.replace('<div class="sheet">', f'<div class="sheet">{_nav(current)}', 1)

    robots = "" if indexable else '\n<meta name="robots" content="noindex, nofollow">'
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{robots}\n"
        f"<title>{html.escape(title)}</title>\n"
        f"<style>{NAV_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def build_index(*, people: int, lanes: int, repos: int, echoes: int, indexable: bool) -> str:
    css = STYLESHEET.read_text(encoding="utf-8") + NAV_CSS + INDEX_CSS
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    body = f"""<div class="sheet">
  {_nav("index.html")}
  <header class="masthead">
    <div class="eyebrow"><span>The Collaborator Constellation</span>
      <span class="sep">/</span><span>updated {stamp}</span></div>
    <h1>The people, and the work that hangs off them</h1>
    <p class="standfirst">
      Two views of one register. Every person and project below is read straight from
      <strong>the register</strong> — nothing on either page is hand-listed, so registering
      someone puts them on the page at the next build.
    </p>
  </header>
  <div class="cards">
    <a class="card" href="/atlas.html">
      <h2>Atlas</h2>
      <p>Every person and the project lanes they are tied to, grouped by how each lane earns
      work, with a build ladder from idea to funnelized.</p>
      <span class="stat">{people} people · {lanes} lanes</span>
      <span class="go">Open the atlas →</span>
    </a>
    <a class="card" href="/streams.html">
      <h2>Streams</h2>
      <p>The register checked against the live estate: work already built that nobody wired to a
      stream, repos sitting in two streams at once, and the same idea built more than once.</p>
      <span class="stat">{repos} repos swept · {echoes} echo families</span>
      <span class="go">Open the streams view →</span>
    </a>
  </div>
  <p class="colophon">
    Built by <code>organs/consulting/constellation/publish-constellation.py</code> from the
    constellation register. Public half only — channel state, boundaries, and private
    repositories are excluded by construction.
  </p>
</div>"""
    robots = "" if indexable else '\n<meta name="robots" content="noindex, nofollow">'
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{robots}\n"
        "<title>The Collaborator Constellation</title>\n"
        f"<style>{css}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n</body>\n</html>\n"
    )


def private_repo_names() -> set[str]:
    if not CENSUS.is_file():
        return set()
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    return {r["name"] for r in census.get("repos", []) if r.get("visibility") == "PRIVATE"}


def already_public_corpus() -> str:
    """Every string GitHub already serves to anonymous visitors.

    Two sources, both genuinely world-readable today:

    - registry.yaml, which lives in a public repository and names some private
      repos outright (`hospes`, `daily-engine`)
    - the name and description of every PUBLIC repository — `etceter4` is a
      private repo, but the public repo `a-mavs-olevm` describes itself as
      "portfolio site (etceter4.com)", so the string is already out there

    Republishing any of this adds no exposure. What the gate must stop is this
    page introducing a private name that is NOT already public — which is
    exactly what the estate sweep can surface.
    """
    parts = []
    registry = HERE / "registry.yaml"
    if registry.is_file():
        parts.append(registry.read_text(encoding="utf-8"))
    if CENSUS.is_file():
        census = json.loads(CENSUS.read_text(encoding="utf-8"))
        for r in census.get("repos", []):
            if r.get("visibility") == "PUBLIC":
                parts.append(r["name"])
                parts.append(r.get("description") or "")
    return "\n".join(parts)


def leak_check(page: str, private: set[str]) -> list[str]:
    """Private repo names the page would introduce to the open internet.

    Two exemptions, both load-bearing:

    - Substring hits do not count. `personal` lives inside the public repo name
      `adaptive-personal-syllabus`; flagging that is a false alarm.
    - Names already served publicly by GitHub do not count — see
      already_public_corpus(). What must never happen is this page introducing
      a private name that is not already out there.
    """
    already_public = already_public_corpus()
    hits = []
    for name in private:
        # Require a delimiter on both sides so a private name embedded in a
        # longer public repo name is not reported.
        pattern = rf"(?<![\w-]){re.escape(name)}(?![\w-])"
        if re.search(pattern, page) and not re.search(pattern, already_public):
            hits.append(name)
    return sorted(hits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=PROJECT, help=f"Cloudflare Pages project (default {PROJECT})")
    ap.add_argument("--dry-run", action="store_true", help="build and check, do not deploy")
    ap.add_argument("--indexable", action="store_true", help="allow search engines (default: noindex)")
    ap.add_argument("--refresh", action="store_true", help="re-sweep the estate before building")
    args = ap.parse_args()

    # ── render the public halves ──
    print("rendering public-safe surfaces…")
    atlas_out = REPO_ROOT / "logs" / "constellation" / "atlas.html"
    streams_out = REPO_ROOT / "logs" / "constellation" / "streams-public.html"

    r = run([sys.executable, str(ATLAS)])
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return 2
    streams_cmd = [sys.executable, str(STREAMS), "--public-safe", "--out", str(streams_out)]
    if args.refresh:
        streams_cmd.append("--refresh")
    r = run(streams_cmd)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return 2

    atlas_frag = atlas_out.read_text(encoding="utf-8")
    streams_frag = streams_out.read_text(encoding="utf-8")

    # ── counts for the index, parsed from what was actually rendered ──
    def figure(frag: str, label: str) -> str:
        m = re.search(rf'<span class="n">(\d+)</span><span class="k">{re.escape(label)}</span>', frag)
        return m.group(1) if m else "?"

    # ── assemble ──
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    pages = {
        "atlas.html": document(atlas_frag, current="atlas.html", indexable=args.indexable),
        "streams.html": document(streams_frag, current="streams.html", indexable=args.indexable),
        "index.html": build_index(
            people=figure(atlas_frag, "people"),
            lanes=figure(atlas_frag, "project lanes"),
            repos=figure(streams_frag, "repos swept"),
            echoes=figure(streams_frag, "echo families"),
            indexable=args.indexable,
        ),
    }

    # ── refuse to publish a private repo name ──
    private = private_repo_names()
    for name, page in pages.items():
        leaked = leak_check(page, private)
        if leaked:
            print(f"ERROR: {name} names private repositories: {leaked}", file=sys.stderr)
            print("Refusing to publish.", file=sys.stderr)
            return 2
    print(f"leak check: clean against {len(private)} private repo names")

    for name, page in pages.items():
        (DIST / name).write_text(page, encoding="utf-8")
        print(f"  {name}  {len(page):,} bytes")

    if args.dry_run:
        print(f"\ndry run — built {DIST}, not deployed")
        return 0

    # ── deploy ──
    env = os.environ.copy()
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*(?:export\s+)?([A-Z0-9_]+)=(.*)$", line)
            if m:
                env.setdefault(m.group(1), m.group(2).strip().strip("\"'"))
    if not env.get("CLOUDFLARE_API_TOKEN"):
        print("ERROR: CLOUDFLARE_API_TOKEN absent — the credential organ owns this", file=sys.stderr)
        return 2

    print(f"\ndeploying to Cloudflare Pages project '{args.project}'…")
    r = run(
        [
            "npx", "--yes", "wrangler@4", "pages", "deploy", str(DIST),
            "--project-name", args.project,
            "--branch", "main",
            "--commit-dirty=true",
        ],
        env=env,
        cwd=str(REPO_ROOT),
    )
    out = (r.stdout or "") + (r.stderr or "")
    # Never echo the raw stream: wrangler prints account context.
    for line in out.splitlines():
        if re.search(r"https://[\w.-]*pages\.dev|Success|Error|error|✨|Uploaded", line):
            print("  " + line.strip())
    if r.returncode != 0:
        return r.returncode

    urls = sorted(set(re.findall(r"https://[\w.-]+\.pages\.dev", out)))
    print("\nlive:")
    for u in urls:
        print(f"  {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
