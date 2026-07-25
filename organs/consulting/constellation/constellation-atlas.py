#!/usr/bin/env python3
"""
constellation-atlas — the one-page visual register of collaborators and their projects.

Renders the Collaborator Constellation register as a single self-contained HTML
page: every person, every project they are tied to, the build stage of each lane,
and the public-face state. No hand-listed people — the register is the only
source, so a new registration appears on the page the next time this runs.

Two render modes, mirroring the register's own two halves:

  public   organs/consulting/constellation/registry.yaml only.
           First-name slugs, projects, tiers, stages, keywords. Safe to publish.

  private  the same, merged with the ARCA-sealed overlay
           (~/Workspace/_people-private/constellation/registry-private.yaml):
           channel state, protocol state, interface budgets, and standing
           boundaries. NEVER publishable — the writer refuses any output path
           inside a git repository so this half cannot reach a remote.

Usage:
  organs/consulting/constellation/constellation-atlas.py                    # public -> logs/constellation/atlas.html
  organs/consulting/constellation/constellation-atlas.py --private --open   # full -> private store, opens it
  organs/consulting/constellation/constellation-atlas.py --out /tmp/a.html
  organs/consulting/constellation/constellation-atlas.py --stdout
"""

from __future__ import annotations

import argparse
import html
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY = REPO_ROOT / "organs" / "consulting" / "constellation" / "registry.yaml"
OVERLAY = Path(
    os.environ.get(
        "LIMEN_CONSTELLATION_OVERLAY",
        str(Path.home() / "Workspace" / "_people-private" / "constellation" / "registry-private.yaml"),
    )
)
PUBLIC_OUT = REPO_ROOT / "logs" / "constellation" / "atlas.html"
PRIVATE_OUT = OVERLAY.parent / "atlas.html"

# The register's declared build ladder. Order is load-bearing: it is the meter.
STAGES = ["idea", "dossier", "building", "mvp", "live", "funnelized"]

# public_face_state enum -> how the page labels it
FACE_LABELS = {
    "none": "no public face",
    "pending-split": "awaiting split",
    "readme": "README",
    "portal": "portal",
    "funnelized": "funnelized",
}

TIER_HEADINGS = {
    "T1": ("Active demand", "Build and funnel now — the lane is pulling."),
    "T2": ("Exists, needs a face", "Real work in flight; the public surface is the gap."),
    "T3": ("Protocol first", "Conversation reviewed before any build. Low or backlog by design."),
}


def _display_name(slug: str) -> str:
    """maddie -> Maddie;  john-f -> John F.;  mike-s -> Mike S."""
    parts = slug.split("-")
    out = [parts[0].capitalize()]
    for p in parts[1:]:
        out.append(f"{p.upper()}." if len(p) == 1 else p.capitalize())
    return " ".join(out)


def _load(path: Path, *, what: str) -> dict[str, Any]:
    if not path.is_file():
        print(f"ERROR: {what} not found at {path}", file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not data.get("people"):
        print(f"ERROR: {what} at {path} declares no people", file=sys.stderr)
        sys.exit(2)
    return data


def _inside_pushable_repo(path: Path) -> bool:
    """True when path lies in a git working tree that has a remote.

    A remote is what makes a path leakable. The private store is deliberately
    git-tracked with NO remote (plus a refusing pre-push hook), so versioning
    the full register there is safe while writing it into any repo that can
    push — this one included — is not.
    """
    probe = path.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent

    in_tree = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        cwd=probe,
        check=False,
    )
    if in_tree.returncode != 0 or in_tree.stdout.strip() != "true":
        return False

    remotes = subprocess.run(["git", "remote"], capture_output=True, text=True, cwd=probe, check=False)
    return bool(remotes.stdout.strip())


def merge(public: dict[str, Any], overlay: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Join the two halves on slug. Public is authoritative for who exists."""
    private_by_slug: dict[str, dict[str, Any]] = {}
    if overlay:
        for row in overlay.get("people", []):
            private_by_slug[row.get("slug", "")] = row

    people = []
    for row in public.get("people", []):
        slug = row.get("slug", "")
        merged = dict(row)
        merged["name"] = _display_name(slug)
        merged["private"] = private_by_slug.get(slug) or {}
        people.append(merged)
    return people


# ── rendering ───────────────────────────────────────────────────────────────

E = html.escape

CSS = """
:root {
  --paper:      #f7f8f7;
  --surface:    #ffffff;
  --ink:        #16201e;
  --ink-muted:  #5c6b67;
  --ink-faint:  #8b9793;
  --rule:       #d8dedb;
  --rule-soft:  #e9edeb;
  --accent:     #0f6b5c;
  --accent-dim: #d9e8e4;
  --shipped:    #2e7d5b;
  --inbuild:    #b8770f;
  --idea:       #6b7b87;
  --dormant:    #9a4c4c;
  --shadow:     0 1px 2px rgba(22, 32, 30, .05), 0 8px 24px -16px rgba(22, 32, 30, .18);

  --display: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  --body: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono: "SF Mono", ui-monospace, SFMono-Regular, Menlo, "IBM Plex Mono", monospace;
}

@media (prefers-color-scheme: dark) {
  :root {
    --paper:      #101614;
    --surface:    #171f1d;
    --ink:        #e6edea;
    --ink-muted:  #9aa8a4;
    --ink-faint:  #6d7b77;
    --rule:       #2a3633;
    --rule-soft:  #202a28;
    --accent:     #4fbfa8;
    --accent-dim: #1d3a35;
    --shipped:    #5cba8c;
    --inbuild:    #d9a13f;
    --idea:       #8b9ba7;
    --dormant:    #c47c7c;
    --shadow:     0 1px 2px rgba(0, 0, 0, .3), 0 8px 24px -16px rgba(0, 0, 0, .6);
  }
}

:root[data-theme="dark"] {
  --paper:      #101614;
  --surface:    #171f1d;
  --ink:        #e6edea;
  --ink-muted:  #9aa8a4;
  --ink-faint:  #6d7b77;
  --rule:       #2a3633;
  --rule-soft:  #202a28;
  --accent:     #4fbfa8;
  --accent-dim: #1d3a35;
  --shipped:    #5cba8c;
  --inbuild:    #d9a13f;
  --idea:       #8b9ba7;
  --dormant:    #c47c7c;
  --shadow:     0 1px 2px rgba(0, 0, 0, .3), 0 8px 24px -16px rgba(0, 0, 0, .6);
}

:root[data-theme="light"] {
  --paper:      #f7f8f7;
  --surface:    #ffffff;
  --ink:        #16201e;
  --ink-muted:  #5c6b67;
  --ink-faint:  #8b9793;
  --rule:       #d8dedb;
  --rule-soft:  #e9edeb;
  --accent:     #0f6b5c;
  --accent-dim: #d9e8e4;
  --shipped:    #2e7d5b;
  --inbuild:    #b8770f;
  --idea:       #6b7b87;
  --dormant:    #9a4c4c;
  --shadow:     0 1px 2px rgba(22, 32, 30, .05), 0 8px 24px -16px rgba(22, 32, 30, .18);
}

body {
  background: var(--paper);
  color: var(--ink);
  font-family: var(--body);
  font-size: 15px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}

.sheet {
  max-width: 1080px;
  margin: 0 auto;
  padding: clamp(24px, 5vw, 64px) clamp(18px, 4vw, 44px) 80px;
  display: flex;
  flex-direction: column;
  gap: 40px;
}

/* ── masthead ─────────────────────────────────────────────── */

.masthead { display: flex; flex-direction: column; gap: 14px; }

.eyebrow {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--accent);
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
}
.eyebrow .sep { color: var(--ink-faint); }

h1 {
  font-family: var(--display);
  font-size: clamp(30px, 5.5vw, 46px);
  line-height: 1.08;
  font-weight: 600;
  letter-spacing: -.01em;
  text-wrap: balance;
  margin: 0;
}

.standfirst {
  max-width: 62ch;
  color: var(--ink-muted);
  font-size: 16px;
}
.standfirst strong { color: var(--ink); font-weight: 600; }

/* ── figures ──────────────────────────────────────────────── */

.figures {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 1px;
  background: var(--rule);
  border: 1px solid var(--rule);
  border-radius: 3px;
  overflow: hidden;
}
.figure {
  background: var(--surface);
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.figure .n {
  font-family: var(--display);
  font-size: 30px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.figure .k {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--ink-faint);
}

/* ── tier strata ──────────────────────────────────────────── */

.stratum { display: flex; flex-direction: column; gap: 18px; }

.stratum-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ink);
}
.tier-mark {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .08em;
  color: var(--surface);
  background: var(--ink);
  padding: 3px 7px;
  border-radius: 2px;
}
.stratum-head h2 {
  font-family: var(--display);
  font-size: 21px;
  font-weight: 600;
  margin: 0;
}
.stratum-head .gloss {
  color: var(--ink-muted);
  font-size: 13.5px;
  flex: 1 1 22ch;
}
.stratum-head .count {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-faint);
  font-variant-numeric: tabular-nums;
}

/* ── person row ───────────────────────────────────────────── */

.person {
  display: grid;
  grid-template-columns: minmax(170px, 210px) 1fr;
  gap: 24px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--rule-soft);
}
.person:last-child { border-bottom: 0; padding-bottom: 0; }

.who { display: flex; flex-direction: column; gap: 6px; }
.who h3 {
  font-family: var(--display);
  font-size: 24px;
  font-weight: 600;
  line-height: 1.1;
  margin: 0;
}
.who .slug {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-faint);
}
.who .tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 2px; }

.pill {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: .06em;
  text-transform: uppercase;
  padding: 2.5px 6px;
  border-radius: 2px;
  border: 1px solid currentColor;
  white-space: nowrap;
}
.pill.on     { color: var(--shipped); }
.pill.warn   { color: var(--inbuild); }
.pill.off    { color: var(--dormant); }
.pill.quiet  { color: var(--ink-faint); }
.pill.mark   { color: var(--accent); }

.budget {
  font-size: 12px;
  color: var(--inbuild);
  line-height: 1.4;
}

.bounds { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.bounds .lbl {
  font-family: var(--mono);
  font-size: 9.5px;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-faint);
}
.bounds li {
  font-size: 12px;
  line-height: 1.45;
  color: var(--ink-muted);
  list-style: none;
  padding-left: 11px;
  position: relative;
}
.bounds li::before {
  content: "";
  position: absolute;
  left: 0;
  top: .55em;
  width: 5px;
  height: 1.5px;
  background: var(--dormant);
}

/* ── project cards ────────────────────────────────────────── */

.lanes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(238px, 1fr));
  gap: 12px;
  align-content: start;
}

.lane {
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 3px;
  box-shadow: var(--shadow);
  padding: 13px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.lane-top { display: flex; flex-direction: column; gap: 3px; }
.lane h4 {
  font-family: var(--body);
  font-size: 14.5px;
  font-weight: 650;
  letter-spacing: -.005em;
  margin: 0;
  line-height: 1.25;
}
.lane .repo {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-faint);
  word-break: break-all;
}
.lane .repo.absent { font-style: italic; }

/* stage ladder — 6 ticks, filled to the lane's current rung */
.ladder { display: flex; flex-direction: column; gap: 5px; }
.ticks { display: flex; gap: 3px; }
.tick {
  height: 4px;
  flex: 1;
  border-radius: 1px;
  background: var(--rule);
}
.tick.lit { background: var(--stage, var(--accent)); }
.ladder .now {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--stage, var(--accent));
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.ladder .now .face { color: var(--ink-faint); }

.keys { display: flex; flex-wrap: wrap; gap: 4px; }
.key {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--ink-muted);
  background: var(--rule-soft);
  border-radius: 2px;
  padding: 2px 5px;
}

.lane .note {
  font-size: 12px;
  line-height: 1.45;
  color: var(--ink-muted);
  border-top: 1px solid var(--rule-soft);
  padding-top: 8px;
}

/* ── legend + colophon ────────────────────────────────────── */

.legend {
  border: 1px solid var(--rule);
  border-radius: 3px;
  background: var(--surface);
  padding: 16px 18px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 18px;
}
.legend section { display: flex; flex-direction: column; gap: 6px; }
.legend h5 {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: .11em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin: 0;
}
.legend p, .legend li { font-size: 12.5px; color: var(--ink-muted); line-height: 1.5; }
.legend ol { list-style: none; display: flex; flex-wrap: wrap; gap: 6px; }
.legend ol li {
  font-family: var(--mono);
  font-size: 10.5px;
  background: var(--rule-soft);
  border-radius: 2px;
  padding: 2px 6px;
  color: var(--ink);
}
.legend ol li .i { color: var(--ink-faint); }

.colophon {
  font-size: 12px;
  color: var(--ink-faint);
  line-height: 1.6;
  border-top: 1px solid var(--rule);
  padding-top: 14px;
}
.colophon code {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-muted);
}

.seal {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--dormant);
  border: 1px solid var(--dormant);
  border-radius: 2px;
  padding: 5px 9px;
  align-self: flex-start;
}

@media (max-width: 620px) {
  .person { grid-template-columns: 1fr; gap: 14px; }
}

@media print {
  body { background: #fff; }
  .lane, .figures, .legend { box-shadow: none; }
}
"""


def _stage_var(stage: str) -> str:
    if stage in ("live", "funnelized"):
        return "var(--shipped)"
    if stage in ("building", "mvp"):
        return "var(--inbuild)"
    return "var(--idea)"


def _ladder(stage: str) -> str:
    """Six ticks lit up to the lane's rung — state as form, not just a word."""
    idx = STAGES.index(stage) if stage in STAGES else 0
    ticks = "".join(
        f'<span class="tick{" lit" if i <= idx else ""}"></span>' for i in range(len(STAGES))
    )
    return ticks


def _lane_html(proj: dict[str, Any]) -> str:
    name = str(proj.get("name", "unnamed"))
    stage = str(proj.get("stage", "idea"))
    face = str(proj.get("public_face_state", "none"))
    repo = proj.get("repo")
    related = proj.get("related_repos") or []
    keywords = proj.get("keywords") or []
    note = proj.get("notes")

    title = name.replace("-", " ")
    if repo:
        repo_line = f'<div class="repo">{E(str(repo))}</div>'
        if related:
            repo_line += f'<div class="repo">+ {len(related)} related</div>'
    else:
        repo_line = '<div class="repo absent">no repository yet</div>'

    keys = "".join(f'<span class="key">{E(str(k))}</span>' for k in keywords[:5])
    note_html = f'<div class="note">{E(str(note).strip())}</div>' if note else ""

    return (
        f'<article class="lane" style="--stage: {_stage_var(stage)}">'
        f'<div class="lane-top"><h4>{E(title)}</h4>{repo_line}</div>'
        f'<div class="ladder"><div class="ticks">{_ladder(stage)}</div>'
        f'<div class="now"><span>{E(stage)}</span>'
        f'<span class="face">{E(FACE_LABELS.get(face, face))}</span></div></div>'
        f'<div class="keys">{keys}</div>'
        f"{note_html}"
        "</article>"
    )


def _person_html(person: dict[str, Any], *, private: bool) -> str:
    slug = str(person.get("slug", ""))
    name = str(person.get("name", slug))
    projects = person.get("projects") or []
    priv = person.get("private") or {}

    tags: list[str] = []
    n = len(projects)
    tags.append(f'<span class="pill quiet">{n} lane{"s" if n != 1 else ""}</span>')
    if person.get("engagement_ref"):
        tags.append('<span class="pill mark">engagement</span>')
    if person.get("funnel_instance_ref"):
        tags.append('<span class="pill on">funnel</span>')

    extras = ""
    if private and priv:
        channel = str(priv.get("channel_state", "")).lower()
        if channel:
            cls = {"active": "on", "in-flight": "warn", "dormant": "off"}.get(channel, "quiet")
            tags.append(f'<span class="pill {cls}">{E(channel)}</span>')
        if priv.get("protocol_state"):
            tags.append(f'<span class="pill quiet">{E(str(priv["protocol_state"]).lower())}</span>')

        budget = priv.get("interface_budget")
        if budget:
            extras += f'<div class="budget">Interface budget: {E(str(budget))}</div>'

        bounds = priv.get("boundaries") or []
        if bounds:
            items = "".join(f"<li>{E(str(b))}</li>" for b in bounds)
            extras += f'<div class="bounds"><span class="lbl">Standing boundaries</span><ul>{items}</ul></div>'

    lanes = "".join(_lane_html(p) for p in projects)

    return (
        '<div class="person">'
        f'<div class="who"><h3>{E(name)}</h3><div class="slug">{E(slug)}</div>'
        f'<div class="tags">{"".join(tags)}</div>{extras}</div>'
        f'<div class="lanes">{lanes}</div>'
        "</div>"
    )


def render(people: list[dict[str, Any]], *, private: bool, version: str) -> str:
    total_people = len(people)
    all_projects = [p for person in people for p in (person.get("projects") or [])]
    total_projects = len(all_projects)
    shipped = sum(1 for p in all_projects if p.get("stage") in ("live", "funnelized"))
    in_build = sum(1 for p in all_projects if p.get("stage") in ("building", "mvp"))
    ideas = sum(1 for p in all_projects if p.get("stage") in ("idea", "dossier"))
    faceless = sum(1 for p in all_projects if p.get("public_face_state") == "none")

    figures = [
        (total_people, "people"),
        (total_projects, "project lanes"),
        (shipped, "live or funnelized"),
        (in_build, "in build"),
        (ideas, "idea stage"),
        (faceless, "no public face"),
    ]
    figures_html = "".join(
        f'<div class="figure"><span class="n">{n}</span><span class="k">{E(k)}</span></div>'
        for n, k in figures
    )

    strata = ""
    for tier in ("T1", "T2", "T3"):
        cohort = [p for p in people if p.get("tier") == tier]
        if not cohort:
            continue
        heading, gloss = TIER_HEADINGS.get(tier, (tier, ""))
        lanes_in_tier = sum(len(p.get("projects") or []) for p in cohort)
        rows = "".join(_person_html(p, private=private) for p in cohort)
        strata += (
            '<section class="stratum">'
            f'<div class="stratum-head"><span class="tier-mark">{E(tier)}</span>'
            f"<h2>{E(heading)}</h2><span class=\"gloss\">{E(gloss)}</span>"
            f'<span class="count">{len(cohort)} people / {lanes_in_tier} lanes</span></div>'
            f"{rows}</section>"
        )

    ladder_legend = "".join(
        f'<li><span class="i">{i + 1}</span> {E(s)}</li>' for i, s in enumerate(STAGES)
    )

    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    mode_label = "full register — private overlay merged" if private else "public-safe half"
    seal = (
        '<div class="seal">Private overlay merged — local only, never publish</div>'
        if private
        else ""
    )
    scope_note = (
        "Channel state, interface budgets, and standing boundaries come from the "
        "ARCA-sealed overlay and appear beside each person."
        if private
        else "Channel state and standing boundaries live in the private overlay and are "
        "deliberately absent here."
    )

    return f"""<title>The Collaborator Constellation</title>
<style>{CSS}</style>
<div class="sheet">
  <header class="masthead">
    <div class="eyebrow">
      <span>Collaborator Constellation</span><span class="sep">/</span>
      <span>{E(version)}</span><span class="sep">/</span>
      <span>{E(mode_label)}</span><span class="sep">/</span>
      <span>{E(stamp)}</span>
    </div>
    <h1>Every person, and the work that hangs off them</h1>
    <p class="standfirst">
      The people in this register and the project lanes each one is tied to — drawn straight
      from <strong>the register</strong>, never hand-listed. Tier says how a lane earns work:
      <strong>T1</strong> is pulling, <strong>T2</strong> exists but has no face,
      <strong>T3</strong> waits on a reviewed conversation before anything gets built.
      {E(scope_note)}
    </p>
    {seal}
  </header>

  <div class="figures">{figures_html}</div>

  {strata}

  <div class="legend">
    <section>
      <h5>Build ladder</h5>
      <ol>{ladder_legend}</ol>
      <p>The six ticks on each lane fill to its current rung.</p>
    </section>
    <section>
      <h5>Reading the lanes</h5>
      <p>Green is shipped, amber is mid-build, grey is still an idea. The right-hand label
      on each lane is its public face — what a stranger can currently see.</p>
    </section>
    <section>
      <h5>Demand gate</h5>
      <p>Review before rails. A T3 lane stays backlogged until the conversation record shows
      real pull, so an idea-stage lane here is a deliberate hold, not a backlog leak.</p>
    </section>
  </div>

  <p class="colophon">
    Generated by <code>organs/consulting/constellation/constellation-atlas.py</code> from
    <code>organs/consulting/constellation/registry.yaml</code>. Add a person to the register
    and they appear here on the next run — this page is never edited by hand.
  </p>
</div>
"""


# ── entrypoint ──────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--private",
        action="store_true",
        help="merge the ARCA-sealed overlay (channel state, boundaries). Output must be outside any git repo.",
    )
    ap.add_argument("--out", type=Path, default=None, help="output path (default depends on mode)")
    ap.add_argument("--stdout", action="store_true", help="write the page to stdout instead of a file")
    ap.add_argument("--open", action="store_true", help="open the rendered page after writing")
    args = ap.parse_args()

    public = _load(REGISTRY, what="constellation register")
    overlay = None
    if args.private:
        overlay = _load(OVERLAY, what="private overlay")

    people = merge(public, overlay)
    page = render(people, private=args.private, version=str(public.get("version", "constellation.v1")))

    if args.stdout:
        if args.private:
            print("ERROR: --private refuses --stdout; the full register is written to a file only", file=sys.stderr)
            return 2
        sys.stdout.write(page)
        return 0

    out = args.out or (PRIVATE_OUT if args.private else PUBLIC_OUT)
    out = out.expanduser().resolve()

    # Containment: the private half must never land somewhere a push could reach.
    if args.private and _inside_pushable_repo(out):
        print(
            f"ERROR: refusing to write the private overlay into a repository with a remote:\n  {out}\n"
            "The full register is local-only. Choose a path in a remote-less store "
            f"(default: {PRIVATE_OUT}).",
            file=sys.stderr,
        )
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    if args.private:
        out.chmod(0o600)

    lanes = sum(len(p.get("projects") or []) for p in people)
    print(f"wrote {out}  ({len(people)} people / {lanes} lanes / {'full' if args.private else 'public-safe'})")

    if args.open:
        subprocess.run(["open", str(out)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
