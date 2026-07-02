#!/usr/bin/env python3
"""launch-organ.py — the home where launch posts belong, made repeatable.

A launch is not a one-off. Every product ships, and every ship needs the same thing: channel-native
posts staged, refined, and fired on the human's word. This organ turns that into ONE repeatable
process: read the product registry (organs/launch/launches.json), stage a channel-native draft per
channel under organs/launch/staged/<product>/<channel>.md, and track each product draft -> staged ->
fired. It NEVER posts — sending is the human's hand (the media organ's Publisher boundary).

  python3 scripts/launch-organ.py --status            # product x channel board
  python3 scripts/launch-organ.py --stage --apply     # stage missing channel drafts (idempotent, never overwrites)
  python3 scripts/launch-organ.py send --product X    # REFUSES — publishing is yours

Staged drafts are never overwritten, so human edits survive re-runs. Briefs are DISCOVERED facts,
never fabricated — the organ only arranges what the registry states.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
REGISTRY = Path(os.environ.get("LIMEN_LAUNCHES", ROOT / "organs" / "launch" / "launches.json"))
STAGED = ROOT / "organs" / "launch" / "staged"


def load() -> dict:
    data = json.loads(REGISTRY.read_text())
    data.setdefault("products", [])
    data.setdefault("channels", [])
    return data


def _footer(p: dict) -> list[str]:
    out = ["", "---", f"- Product: {p['name']} — {p.get('url', '')}".rstrip(" —")]
    if p.get("install"):
        out.append(f"- Install: {p['install']}")
    if p.get("source_post") and p.get("repo"):
        out.append(f"- Fuller draft to mine for copy: {p['repo']}/{p['source_post']}")
    out.append("")
    out.append("> DRAFT — refine the voice, then post by hand. The organ does not send.")
    return out


def build_hn(p: dict) -> str:
    lines = [
        f"# Show HN: {p['name']} — {p.get('one_liner', '')}".rstrip(" —"),
        "",
        "## Title",
        f"Show HN: {p['name']} — {p.get('one_liner', '')}".rstrip(" —"),
        "",
        "## First comment",
        "",
    ]
    if p.get("why_built"):
        lines.append(f"I built this because {p['why_built']}.")
        lines.append("")
    lines.append(f"What it is: {p.get('one_liner', p['name'])}.")
    if p.get("proof"):
        lines.append("")
        lines.append(f"Details: {p['proof']}.")
    if p.get("url") or p.get("install"):
        lines.append("")
        lines.append(f"Link: {p.get('install') or p.get('url')}")
    lines += _footer(p)
    return "\n".join(lines)


def build_reddit(p: dict) -> str:
    lines = [
        f"# Reddit — {p['name']}",
        "",
        "> Pick the subreddit and read its self-promotion rules FIRST. Lead with the problem; disclose you built it.",
        "",
        "## Title",
        f"{p['name']}: {p.get('one_liner', '')}".rstrip(" :"),
        "",
        "## Body",
        "",
    ]
    if p.get("why_built"):
        lines.append(f"The problem: {p['why_built']}.")
        lines.append("")
    lines.append(f"I built {p['name']} to fix that — {p.get('one_liner', '')}.".replace(" — .", "."))
    if p.get("audience"):
        lines.append("")
        lines.append(f"It's for {p['audience']}.")
    if p.get("proof"):
        lines.append("")
        lines.append(f"Where it stands: {p['proof']}.")
    lines += _footer(p)
    return "\n".join(lines)


def build_producthunt(p: dict) -> str:
    tagline = (p.get("one_liner", p["name"]))[:60]
    lines = [
        f"# Product Hunt — {p['name']}",
        "",
        "## Tagline (<= 60 chars)",
        tagline,
        "",
        "## Description",
        p.get("proof", p.get("one_liner", "")),
        "",
        "## Maker's first comment",
        "",
        f"Hi PH — I made {p['name']}. {p.get('why_built', '').capitalize()}."
        if p.get("why_built") else f"Hi PH — I made {p['name']}.",
    ]
    lines += _footer(p)
    return "\n".join(lines)


BUILDERS = {"hn": build_hn, "reddit": build_reddit, "producthunt": build_producthunt}


def build(channel_id: str, p: dict) -> str:
    fn = BUILDERS.get(channel_id)
    if fn:
        return fn(p)
    # generic fallback for a channel with no dedicated builder
    lines = [f"# {channel_id} — {p['name']}", "", p.get("one_liner", ""), "", p.get("proof", "")]
    return "\n".join(lines + _footer(p))


def stage(data: dict, apply: bool) -> int:
    created = existing = 0
    for p in data["products"]:
        for ch in p.get("channels", []):
            target = STAGED / p["id"] / f"{ch}.md"
            if target.exists():
                existing += 1
                print(f"  exists   {p['id']}/{ch}.md")
                continue
            created += 1
            if apply:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(build(ch, p) + "\n")
                print(f"  STAGED   {p['id']}/{ch}.md")
            else:
                print(f"  would stage  {p['id']}/{ch}.md")
    verb = "staged" if apply else "would stage"
    print(f"\n{verb} {created} draft(s); {existing} already present (never overwritten).")
    if created and not apply:
        print("Re-run with --apply to write them.")
    return 0


def status(data: dict) -> int:
    print(f"launch board  ({len(data['products'])} product(s))")
    for p in data["products"]:
        print(f"\n  {p['name']}  [{p.get('status', 'draft')}]  {p.get('url', '')}")
        for ch in p.get("channels", []):
            target = STAGED / p["id"] / f"{ch}.md"
            mark = "staged" if target.exists() else "—"
            fired = " · FIRED" if p.get("status") == "fired" else ""
            print(f"      {ch:14} {mark}{fired}")
    print("\nsend is the human's hand — the organ never posts.")
    return 0


def send(product_id: str) -> int:
    print(f"REFUSED: launch-organ does not post. '{product_id}' is a SEND — the human's hand.")
    print("Refine organs/launch/staged/<product>/<channel>.md, post it yourself, then set status: fired.")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("verb", nargs="?", default="status", choices=["status", "stage", "send"])
    ap.add_argument("--status", action="store_true", help="show the product x channel board")
    ap.add_argument("--stage", action="store_true", help="stage missing channel drafts")
    ap.add_argument("--apply", action="store_true", help="write files (with --stage); default is a dry-run")
    ap.add_argument("--product", default="", help="product id (for send)")
    args = ap.parse_args()

    data = load()
    if args.stage or args.verb == "stage":
        return stage(data, args.apply)
    if args.verb == "send":
        return send(args.product or "<product>")
    return status(data)


if __name__ == "__main__":
    raise SystemExit(main())
