#!/usr/bin/env python3
"""generate-positioning — step 1 of the inbound-magnet system (docs/inbound-magnet-system.md).
# Gate authority: organs/governance/PUBLICATION-POLICY.md — convergence table row 4 (awaiting_publish).
# The `awaiting_publish` flag IS the `PUBLISH`→his_lever manifestation: the publication-policy engine
# decides content disposition; this flag gates whether the fully-authored content actually renders
# (his hand to flip). Changes to the publish gate start in the publication policy, not here.

A repo pulls a warm inbound lead by *existing* only if its surface tells the right buyer,
in their own language, that (a) it solves an expensive problem of theirs and (b) the person
who built it does not work for free. This generator renders that surface — one positioning
artifact per value-repo — from a curated judgment layer (`positioning-seeds.json`) plus the
repo's own production-grade proof signals.

It emits TWO sinks per repo, and the split is the point:

  • PUBLIC  docs/positioning/{slug}.md           — buyer · the expensive problem · cost of not
      having it · the RPG engagement ladder (names + what-they-get + cadence) · proof signals ·
      what's OPEN vs the running ENGINE you rent (the form/operation split — the code is the lure,
      not the leak) · the two-door CTA.  CONTAINS NO PRICES. A hard guard refuses to write it if a
      currency token ever leaks in — "no dollar signs on the page" is enforced by the tool, not care.

The two-door CTA is the capture funnel: when the seeds' frontdoor block carries a `contact`, each
CTA renders as a `mailto:` pre-tagged with the repo + door (deploy=client / hire=recruiter), so a
click lands already-classified in the existing inbox triage. No contact set → plain CTA text (we
never publish an address he hasn't chosen). Nothing is ever sent — capture, not outreach.
  • INTERNAL docs/positioning/{slug}.internal.md — the price anchors, clearly stamped
      NOT FOR PUBLICATION. Anchors live ONLY here, so they physically cannot reach the page.

Two doors, one surface (see the plan): the deepest ladder level — "be our data org on retainer"
— is the same conversation as "come run our data org for $180k," so the page that opens the
client door opens the recruiter door.

Read-only by default (prints the plan + the rendered public page to stdout). With --apply it
writes both artifacts atomically. Never dispatches, never sends, never touches a deploy path.

Usage:
  python scripts/generate-positioning.py [--repo owner/name] [--apply] [--fetch]
    --repo    one repo (owner/name); default = every repo in value-repos.json that has a seed
    --apply   write the artifacts (default: dry-run, print only)
    --fetch   best-effort overlay live signals via `gh` (description/topics/homepage);
              off by default so the generator is deterministic and offline-testable
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))


def _value_repos_path() -> Path:
    return Path(os.environ.get("LIMEN_VALUE_REPOS", LIMEN_ROOT / "value-repos.json"))


def _seeds_path() -> Path:
    return Path(os.environ.get("LIMEN_POSITIONING_SEEDS", LIMEN_ROOT / "positioning-seeds.json"))


def _out_dir() -> Path:
    return Path(os.environ.get("LIMEN_POSITIONING_DIR", LIMEN_ROOT / "docs" / "positioning"))


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _value_repos(path: Path) -> list[str]:
    """Accept both string ("owner/repo") and object ({"repo": "owner/repo"}) entries."""
    data = _load_json(path)
    out = []
    for entry in data.get("repos", []):
        if isinstance(entry, str):
            out.append(entry)
        elif isinstance(entry, dict) and entry.get("repo"):
            out.append(entry["repo"])
    return out


def _slug(repo: str) -> str:
    return repo.split("/", 1)[-1]


# A seed can be fully authored + proof-verified before its repo is public. The whole doctrine is
# "publish the form" — a PRIVATE repo is no lure at all: the GitHub link 404s for every buyer, and
# the positioning page itself (committed to the *public* limen repo) would advertise a system no
# one can see. Flipping a repo public exposes his source — that's his hand, never ours. So a seed
# marked `awaiting_publish` is banked and tested but kept OFF every public surface until the repo
# is live; clearing the flag (his switch, one line) is all that stands between it and rendering.
def _awaiting_publish(seed: dict) -> bool:
    return bool(seed.get("awaiting_publish"))


# --- capture funnel -------------------------------------------------------------------------
# The cheapest capture that actually works today: the CTA is a `mailto:` whose subject is
# pre-tagged with the repo and the door (deploy = client, hire = recruiter). A click lands in
# his existing inbox, already classified by which system and which audience — so the live
# obligations triage routes it with zero new infrastructure and nothing is ever auto-sent.
# Gated on a configured `contact` in the seeds' frontdoor block: no contact → plain CTA text
# (so we never publish an address he hasn't chosen to expose).

def _mailto(contact: str, slug: str | None, door: str) -> str:
    tag = f"[{slug} · {door}]" if slug else f"[front door · {door}]"
    subject = quote(f"{tag} — inbound", safe="")
    return f"mailto:{contact}?subject={subject}"


def _cta(label: str, contact: str | None, slug: str | None, door: str) -> str:
    """A CTA as a tagged-mailto link when a contact is configured; plain bold text otherwise."""
    if contact:
        return f"**[{label}]({_mailto(contact, slug, door)}) →**"
    return f"**{label} →**"


# A currency / price token anywhere in the PUBLIC page is a contract violation. Catch $€£, a
# bare "<num>k" band, and "/mo" cadence shorthand — the shapes prices take in the seed anchors.
_PRICE_RE = re.compile(r"[$€£]|\b\d[\d,]*\s*k\b|/\s*mo\b", re.IGNORECASE)


def _assert_no_prices(markdown: str, repo: str) -> None:
    hits = _PRICE_RE.findall(markdown)
    if hits:
        raise ValueError(
            f"refusing to emit PUBLIC positioning for {repo}: price/currency token(s) leaked "
            f"onto the page ({hits!r}). Anchors belong in the .internal artifact only."
        )


def _fetch_signals(repo: str) -> dict:
    """Best-effort live overlay via gh. Degrades to {} on any failure — never blocks."""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}", "--jq",
             "{description: .description, homepage: .homepage, topics: .topics, "
             "pushed_at: .pushed_at, language: .language}"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout.strip()
        return json.loads(out) if out else {}
    except Exception:
        return {}


def render_public(repo: str, seed: dict, signals: dict | None = None,
                  contact: str | None = None) -> str:
    """Render the public positioning page. No prices — enforced by the caller's guard."""
    signals = signals or {}
    name = seed.get("display_name", _slug(repo))
    lines: list[str] = []
    lines.append(f"# {name}")
    lines.append("")
    lines.append(f"<!-- generated by scripts/generate-positioning.py from positioning-seeds.json · repo: {repo} -->")
    lines.append("")
    if seed.get("what_it_is"):
        lines.append(seed["what_it_is"])
        lines.append("")

    # Proof signals — the production-grade weight that signals "this is not free," not a price.
    proof = list(seed.get("proof_signals", []))
    if signals.get("topics"):
        proof_topics = ", ".join(signals["topics"][:8])
        if proof_topics:
            proof.append(f"topics: {proof_topics}")
    if proof:
        lines.append("**Built to production weight:** " + " · ".join(proof) + ".")
        lines.append("")

    if seed.get("buyer"):
        lines.append(f"**Who this is for:** {seed['buyer']}")
        lines.append("")
    if seed.get("expensive_problem"):
        lines.append(f"**The expensive problem:** {seed['expensive_problem']}")
        lines.append("")
    if seed.get("cost_of_not_having_it"):
        lines.append(f"**What it costs you to not have this:** {seed['cost_of_not_having_it']}")
        lines.append("")

    ladder = seed.get("ladder", [])
    if ladder:
        lines.append("## Ways to work together")
        lines.append("")
        lines.append("Pick the depth that fits. Each level is a deeper build than the last.")
        lines.append("")
        lines.append("| Path | What you get | Cadence |")
        lines.append("|------|--------------|---------|")
        for step in ladder:
            n = step.get("name", "")
            kind = step.get("kind", "")
            label = f"**{step.get('level', '')} · {n}**" + (f" ({kind})" if kind else "")
            lines.append(f"| {label} | {step.get('what_they_get', '')} | {step.get('cadence', '')} |")
        lines.append("")

    # Form vs. operation — the doctrine made concrete (see publish-form-rent-operation).
    # The code being open is the lure, not the leak: what you pay for is the running, fed
    # engine, which no fork clones. Naming that distinction on the page is the strongest
    # value signal there is — it tells the buyer exactly why "it's all public" and "you'll
    # pay" are both true. No prices (the caller guards this text too).
    public_face = seed.get("public_face")
    private_operation = seed.get("private_operation")
    if public_face or private_operation:
        lines.append("## What's open — and what you're buying")
        lines.append("")
        if public_face:
            lines.append(f"**Open:** {public_face}")
            lines.append("")
        if private_operation:
            lines.append(f"**What you're buying:** {private_operation}")
            lines.append("")

    cta_client = seed.get("cta_client", "Deploy this for your shop")
    cta_recruiter = seed.get("cta_recruiter", "Work with the team that built this")
    slug = _slug(repo)
    lines.append("---")
    lines.append("")
    lines.append(f"{_cta(cta_client, contact, slug, 'deploy')}  ·  "
                 f"{_cta(cta_recruiter, contact, slug, 'hire')}")
    lines.append("")
    lines.append("_If it fits, reach out — this conversation starts at serious._")
    lines.append("")
    return "\n".join(lines)


def render_frontdoor(repos_seeds: list[tuple[str, dict]], frontdoor: dict) -> str:
    """Render the universal front door — the two-door landing surface (profile-README shaped).

    Aggregates every positioned repo into one page: a builder-identity headline, the two doors
    stated once (client + recruiter), then a card per repo with its hook, proof signals, and a
    link. No prices (the caller guards). One surface, both audiences."""
    fd = frontdoor or {}
    lines: list[str] = []
    lines.append("<!-- generated by scripts/generate-positioning.py --frontdoor from positioning-seeds.json -->")
    lines.append("")
    lines.append(f"# {fd.get('headline', 'I build production systems that solve expensive problems.')}")
    lines.append("")
    if fd.get("subhead"):
        lines.append(fd["subhead"])
        lines.append("")
    contact = fd.get("contact") or None
    client = fd.get("door_client", {})
    recruiter = fd.get("door_recruiter", {})
    if client:
        lines.append(_cta(client.get("label", "Deploy it for your shop"), contact, None, "deploy"))
        if client.get("blurb"):
            lines.append(f"> {client['blurb']}")
        lines.append("")
    if recruiter:
        lines.append(_cta(recruiter.get("label", "Work with the builder"), contact, None, "hire"))
        if recruiter.get("blurb"):
            lines.append(f"> {recruiter['blurb']}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## The systems")
    lines.append("")
    for repo, seed in repos_seeds:
        name = seed.get("display_name", _slug(repo))
        lines.append(f"### [{name}](https://github.com/{repo})")
        lines.append("")
        if seed.get("what_it_is"):
            lines.append(seed["what_it_is"])
            lines.append("")
        proof = seed.get("proof_signals", [])
        if proof:
            lines.append("`" + "` · `".join(proof) + "`")
            lines.append("")
        if seed.get("expensive_problem"):
            lines.append(f"**Solves:** {seed['expensive_problem']}")
            lines.append("")
        cta = seed.get("cta_client", "Deploy this for your shop")
        lines.append(f"→ **{cta}** · see [the ways to work together](docs/positioning/{_slug(repo)}.md)")
        lines.append("")
    if fd.get("closing"):
        lines.append("---")
        lines.append("")
        lines.append(f"_{fd['closing']}_")
        lines.append("")
    return "\n".join(lines)


# GitHub topic rules: lowercase, alphanumeric + hyphens, no leading/trailing hyphen, <=35 chars,
# <=20 per repo. We validate (not silently mangle) so a bad seed topic is surfaced, not hidden.
_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,34}$")


def _validate_topics(topics: list[str]) -> tuple[list[str], list[str]]:
    good, bad = [], []
    for t in topics:
        (good if _TOPIC_RE.match(t) else bad).append(t)
    return good[:20], bad  # GitHub caps at 20 topics/repo


def _current_topics(repo: str) -> list[str] | None:
    """Best-effort current topics via gh. None on failure (so the report says 'unknown')."""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/topics",
             "-H", "Accept: application/vnd.github+json", "--jq", ".names[]"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout.strip()
        return [ln for ln in out.splitlines() if ln] if out else []
    except Exception:
        return None


def render_discoverability(repos_seeds: list[tuple[str, dict]], *, fetch: bool) -> str:
    """Per-repo buyer-search topics + SEO description + the exact apply commands.

    This RECOMMENDS — it never mutates a public repo. Applying topics/description to a public
    repo is an outward-facing change to his identity; the report hands him copy-paste `gh`
    commands so the act stays explicit and his."""
    lines: list[str] = []
    lines.append("<!-- generated by scripts/generate-positioning.py --discoverability -->")
    lines.append("")
    lines.append("# Discoverability recommendations")
    lines.append("")
    lines.append("Buyer-search topics + SEO description per repo, so the right buyer *finds* the")
    lines.append("repo by searching their own problem. **Nothing here is applied automatically** —")
    lines.append("setting topics/description on a public repo is an outward-facing change; run the")
    lines.append("commands below when you want them live.")
    lines.append("")
    for repo, seed in repos_seeds:
        name = seed.get("display_name", _slug(repo))
        topics = list(seed.get("search_topics", []))
        good, bad = _validate_topics(topics)
        desc = seed.get("seo_description", "")
        _assert_no_prices(desc, repo)  # SEO copy carries no prices either
        lines.append(f"## {name} — `{repo}`")
        lines.append("")
        if fetch:
            cur = _current_topics(repo)
            lines.append(f"- **Current topics:** {', '.join(cur) if cur else ('(none)' if cur == [] else '(unknown — gh fetch failed)')}")
        lines.append(f"- **Recommended topics:** {', '.join(good) if good else '(none)'}")
        if bad:
            lines.append(f"- ⚠ **Invalid topics (fix in seed):** {', '.join(bad)}")
        if desc:
            lines.append(f"- **Recommended description:** {desc}")
        lines.append("")
        if good:
            topic_flags = " ".join(f"-f 'names[]={t}'" for t in good)
            lines.append("```sh")
            lines.append("# apply topics (his hand — outward-facing public change):")
            lines.append(f"gh api -X PUT repos/{repo}/topics \\")
            lines.append("  -H 'Accept: application/vnd.github+json' \\")
            lines.append(f"  {topic_flags}")
            if desc:
                lines.append("# apply description:")
                lines.append(f"gh repo edit {repo} --description {json.dumps(desc, ensure_ascii=False)}")
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def render_internal(repo: str, seed: dict) -> str:
    """Render the internal anchor sheet. NEVER published. Prices live ONLY here."""
    name = seed.get("display_name", _slug(repo))
    lines: list[str] = []
    lines.append(f"# INTERNAL — price anchors · {name}")
    lines.append("")
    lines.append("> **NOT FOR PUBLICATION.** These are internal proposal anchors — defensible bands to")
    lines.append("> negotiate *up* from, never shown on the page. The public artifact carries no prices.")
    lines.append("")
    lines.append(f"Repo: `{repo}`")
    lines.append("")
    ladder = seed.get("ladder", [])
    if ladder:
        lines.append("| Path | Internal anchor | Cadence |")
        lines.append("|------|-----------------|---------|")
        for step in ladder:
            label = f"**{step.get('level', '')} · {step.get('name', '')}**"
            lines.append(f"| {label} | {step.get('internal_anchor', '—')} | {step.get('cadence', '')} |")
        lines.append("")
    if seed.get("recruiter_bridge_level"):
        lines.append(
            f"**Recruiter bridge:** level {seed['recruiter_bridge_level']} "
            "(\"be our data org on retainer\") is the same conversation as a senior-hire offer — "
            "the page that opens this client path opens the employer door."
        )
        lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def census() -> dict:
    """Redacted positioning census: aggregate seed/artifact shape only, never repo names or copy."""
    report = {
        "value_repos_present": _value_repos_path().exists(),
        "value_repos_readable": False,
        "value_repo_count": 0,
        "seeds_present": _seeds_path().exists(),
        "seeds_readable": False,
        "seed_repo_count": 0,
        "seeded_value_repo_count": 0,
        "publishable_seed_count": 0,
        "awaiting_publish_count": 0,
        "missing_seed_count": 0,
        "frontdoor_configured": False,
        "contact_configured": False,
        "repo_topic_seed_count": 0,
        "valid_topic_count": 0,
        "invalid_topic_count": 0,
        "seo_description_count": 0,
        "ladder_step_count": 0,
        "internal_anchor_count": 0,
        "out_dir_present": _out_dir().exists(),
        "public_artifact_count": 0,
        "internal_artifact_count": 0,
        "system_artifact_count": 0,
    }
    try:
        value_repos = _value_repos(_value_repos_path())
        report["value_repos_readable"] = True
        report["value_repo_count"] = len(value_repos)
    except Exception:
        value_repos = []

    try:
        doc = _load_json(_seeds_path())
        seeds = doc.get("repos", {}) if isinstance(doc.get("repos", {}), dict) else {}
        frontdoor = doc.get("frontdoor", {}) if isinstance(doc.get("frontdoor", {}), dict) else {}
        report["seeds_readable"] = True
        report["seed_repo_count"] = len(seeds)
        report["frontdoor_configured"] = bool(frontdoor)
        report["contact_configured"] = bool(frontdoor.get("contact"))
    except Exception:
        seeds = {}

    seeded_value_repos = [repo for repo in value_repos if repo in seeds]
    report["seeded_value_repo_count"] = len(seeded_value_repos)
    report["awaiting_publish_count"] = sum(1 for repo in seeded_value_repos if _awaiting_publish(seeds[repo]))
    report["publishable_seed_count"] = report["seeded_value_repo_count"] - report["awaiting_publish_count"]
    report["missing_seed_count"] = max(0, report["value_repo_count"] - report["seeded_value_repo_count"])

    for seed in seeds.values():
        if not isinstance(seed, dict):
            continue
        topics = seed.get("search_topics") if isinstance(seed.get("search_topics"), list) else []
        if topics:
            report["repo_topic_seed_count"] += 1
            good, bad = _validate_topics([str(topic) for topic in topics])
            report["valid_topic_count"] += len(good)
            report["invalid_topic_count"] += len(bad)
        if seed.get("seo_description"):
            report["seo_description_count"] += 1
        ladder = seed.get("ladder") if isinstance(seed.get("ladder"), list) else []
        report["ladder_step_count"] += len(ladder)
        report["internal_anchor_count"] += sum(1 for step in ladder if isinstance(step, dict) and step.get("internal_anchor"))

    out_dir = _out_dir()
    if out_dir.is_dir():
        for path in out_dir.glob("*.md"):
            name = path.name
            if name.endswith(".internal.md"):
                report["internal_artifact_count"] += 1
            elif name.startswith("_"):
                report["system_artifact_count"] += 1
            else:
                report["public_artifact_count"] += 1
    return report


def generate_for(repo: str, seed: dict, *, apply: bool, fetch: bool, out_dir: Path,
                 contact: str | None = None) -> dict:
    signals = _fetch_signals(repo) if fetch else {}
    public = render_public(repo, seed, signals, contact=contact)
    _assert_no_prices(public, repo)  # hard guard before anything is written
    internal = render_internal(repo, seed)
    slug = _slug(repo)
    public_path = out_dir / f"{slug}.md"
    internal_path = out_dir / f"{slug}.internal.md"
    if apply:
        _atomic_write(public_path, public)
        _atomic_write(internal_path, internal)
    return {
        "repo": repo,
        "public_path": str(public_path),
        "internal_path": str(internal_path),
        "public": public,
        "internal": internal,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate inbound positioning artifacts per value-repo.")
    ap.add_argument("--repo", help="one repo (owner/name); default = all seeded value-repos")
    ap.add_argument("--apply", action="store_true", help="write artifacts (default: dry-run)")
    ap.add_argument("--fetch", action="store_true", help="best-effort live signal overlay via gh")
    ap.add_argument("--out-profile", action="store_true",
                    help="with --frontdoor: also stage the org-profile README artifact (org hub)")
    ap.add_argument("--frontdoor", action="store_true",
                    help="render the aggregate two-door front door over all seeded value-repos")
    ap.add_argument("--discoverability", action="store_true",
                    help="render buyer-search topics + SEO + apply-commands per repo (recommends, never mutates)")
    ap.add_argument("--census", action="store_true", help="print redacted positioning seed/artifact counts and exit")
    args = ap.parse_args(argv)

    if args.census:
        print(json.dumps(census(), indent=2, sort_keys=True))
        return 0

    doc = _load_json(_seeds_path())
    seeds = doc.get("repos", {})
    out_dir = _out_dir()
    contact = (doc.get("frontdoor", {}) or {}).get("contact") or None

    if args.frontdoor:
        ordered = [(r, seeds[r]) for r in _value_repos(_value_repos_path())
                   if r in seeds and not _awaiting_publish(seeds[r])]
        if not ordered:
            print("generate-positioning: no seeded value-repos to render a front door from.",
                  file=sys.stderr)
            return 0
        page = render_frontdoor(ordered, doc.get("frontdoor", {}))
        _assert_no_prices(page, "FRONTDOOR")  # same hard no-price guard as per-repo pages
        fd_path = out_dir / "_frontdoor.md"
        if args.apply:
            _atomic_write(fd_path, page)
        verb = "WROTE" if args.apply else "would write"
        print(f"=== FRONTDOOR — {verb} {fd_path} ({len(ordered)} systems) ===")
        if args.out_profile:
            # the org-hub artifact: same front door, headed for organvm/.github/profile/README.md
            # (the one README GitHub renders on the org page — the hub of the hub-and-spoke lure
            # graph). A fleet task ships it by PR on the .github repo; this only stages the copy.
            profile = (
                "<!-- generated by scripts/generate-positioning.py --frontdoor --out-profile -->\n"
                "<!-- SHIP TO: organvm/.github/profile/README.md (by PR on that repo) -->\n\n" + page
            )
            pf_path = out_dir / "org-profile-README.md"
            if args.apply:
                _atomic_write(pf_path, profile)
            print(f"=== ORG PROFILE — {verb} {pf_path} ===")
        if not args.apply:
            print(page)
        return 0

    if args.discoverability:
        ordered = [(r, seeds[r]) for r in _value_repos(_value_repos_path())
                   if r in seeds and not _awaiting_publish(seeds[r])]
        if not ordered:
            print("generate-positioning: no seeded value-repos for a discoverability pass.",
                  file=sys.stderr)
            return 0
        page = render_discoverability(ordered, fetch=args.fetch)
        disc_path = out_dir / "_discoverability.md"
        if args.apply:
            _atomic_write(disc_path, page)
        verb = "WROTE" if args.apply else "would write"
        print(f"=== DISCOVERABILITY — {verb} {disc_path} ({len(ordered)} repos) ===")
        if not args.apply:
            print(page)
        return 0

    held = []
    if args.repo:
        targets = [args.repo]
    else:
        all_value = [r for r in _value_repos(_value_repos_path()) if r in seeds]
        # Surface (never silently drop) the verified-but-private repos: they're authored and
        # banked, waiting only on his publish switch. Logged below so the hold is visible.
        held = [r for r in all_value if _awaiting_publish(seeds[r])]
        targets = [r for r in all_value if not _awaiting_publish(seeds[r])]

    if not targets:
        print("generate-positioning: no seeded value-repos to render. Add entries to "
              f"{_seeds_path()}.", file=sys.stderr)
        return 0

    rendered = 0
    skipped = []
    for repo in targets:
        seed = seeds.get(repo)
        if not seed:
            skipped.append(repo)
            continue
        # Never render a public artifact for a repo that isn't public yet — even when named
        # explicitly with --repo. The page lives in the public limen repo and links to a 404.
        if _awaiting_publish(seed):
            held.append(repo)
            continue
        result = generate_for(repo, seed, apply=args.apply, fetch=args.fetch, out_dir=out_dir,
                              contact=contact)
        rendered += 1
        verb = "WROTE" if args.apply else "would write"
        print(f"\n=== {repo} — {verb} {result['public_path']} (+ .internal) ===")
        if not args.apply:
            print(result["public"])

    if held:
        print(f"\ngenerate-positioning: {len(held)} repo(s) authored + verified but "
              f"AWAITING PUBLISH (private repo → not rendered until it's public): "
              f"{', '.join(held)}", file=sys.stderr)
    if skipped:
        print(f"\ngenerate-positioning: {len(skipped)} repo(s) have no seed yet "
              f"(positioning not yet authored): {', '.join(skipped)}", file=sys.stderr)
    print(f"\ngenerate-positioning: {rendered} repo(s) "
          f"{'written' if args.apply else 'rendered (dry-run)'}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
