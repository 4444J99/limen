#!/usr/bin/env python3
"""repo-metadata-sync.py — the repo-metadata effector: description / topics / homepage per public repo.

The missing sink for estate.yaml's `repo.desired` (topics/description/homepage were declared with no
machine effector — render_discoverability only ever printed copy-paste commands). Desired values
resolve in three layers, judgment above derivation:

  1. positioning-seeds.json (the curated value repos: `seo_description`, `search_topics`) — the seed
     is his authored judgment, so it WINS over live values. `awaiting_publish` rows are skipped.
  2. institutio/github/seo-seeds.yaml `repos:` rows — the thin judgment overlay for the tail.
  3. Deterministic derivation, FILL-GAPS-NEVER-OVERWRITE: keep any live human-set value; when a gap
     exists, description ← README first paragraph (≤350, price-clean), topics ← current ∪ (name
     tokens + language + baseline) capped at 20, homepage ← the defaults.homepage portal edge.

Idempotent: run #2 plans 0 writes. Bounded (LIMEN_REPO_METADATA_MAX per run). DOUBLE-DARK: mutation
requires --apply AND LIMEN_REPO_METADATA_APPLY=1 (arming lever L-SEO-METADATA) — outward-facing but
reversible, so an armed valve is legitimate; visibility stays apply-visibility.py's lane.

  python3 scripts/repo-metadata-sync.py             # dry plan table
  python3 scripts/repo-metadata-sync.py --check     # sensor idiom: exit 0 ⟺ no metadata drift
  python3 scripts/repo-metadata-sync.py --apply     # mutate (double-dark, bounded)
  python3 scripts/repo-metadata-sync.py --suggest   # draft seo-seeds.yaml rows for curation (never applied)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.resolve()
SEO_SEEDS = ROOT / "institutio" / "github" / "seo-seeds.yaml"
POSITIONING_SEEDS = ROOT / "positioning-seeds.json"

sys.path.insert(0, str(SCRIPT_DIR))

_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,34}$")
_PRICE_RE = re.compile(r"[$€£]|\b\d[\d,]*\s*k\b|/\s*mo\b", re.IGNORECASE)
_STOP = {"the", "and", "for", "with", "into", "from", "this", "that", "a-i"}


def _module(name: str, filename: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _gh(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _seeds() -> tuple[dict, dict, str]:
    """(positioning rows, seo-seed rows, default homepage)."""
    try:
        pos = json.loads(POSITIONING_SEEDS.read_text(encoding="utf-8")).get("repos") or {}
    except Exception:
        pos = {}
    try:
        seo = yaml.safe_load(SEO_SEEDS.read_text(encoding="utf-8")) or {}
    except Exception:
        seo = {}
    default_home = str((seo.get("defaults") or {}).get("homepage") or "https://github.com/organvm")
    return pos, seo.get("repos") or {}, default_home


def _derive_description(repo: str) -> str:
    """README first paragraph, ≤350, price-clean. '' when nothing derivable."""
    r = _gh(["api", f"/repos/{repo}/readme", "--jq", ".content"])
    if r.returncode != 0:
        return ""
    try:
        text = base64.b64decode(r.stdout.strip()).decode("utf-8", errors="replace")
    except Exception:
        return ""
    for block in re.split(r"\n\s*\n", text):
        block = " ".join(block.strip().split())
        if block and not block.startswith(("#", "!", "<", "[!", "```", "|", ">")):
            block = re.sub(r"[\[\]`*_]", "", block)
            if _PRICE_RE.search(block):
                continue
            return block[:347] + "…" if len(block) > 350 else block
    return ""


def _derive_topics(row: dict) -> list[str]:
    """Deterministic from the repo name + language: the search tokens a stranger would type."""
    name = str(row.get("full_name", "")).split("/", 1)[-1].lower()
    toks = [t for t in re.split(r"[-_.]+", name) if len(t) >= 3 and t not in _STOP]
    lang = str(row.get("language") or "").lower().replace(" ", "-")
    if lang and _TOPIC_RE.match(lang):
        toks.append(lang)
    seen: list[str] = []
    for t in toks:
        if _TOPIC_RE.match(t) and t not in seen:
            seen.append(t)
    return seen


def _current(repo: str) -> dict | None:
    r = _gh(["api", f"/repos/{repo}", "--jq", "{description, homepage, topics, language}"])
    try:
        return json.loads(r.stdout) if r.returncode == 0 else None
    except Exception:
        return None


def desired_for(row: dict, pos: dict, seo_rows: dict, default_home: str, seo_block: dict) -> dict:
    """The desired metadata triple for one repo. Pure given its inputs (derivation reads live only
    for description when a gap exists — the caller passes the fetched value via row['_derived'])."""
    repo = str(row["full_name"])
    cur_desc = str(row.get("description") or "").strip()
    cur_home = str(row.get("homepage") or "").strip()
    n_topics = int(row.get("topics_count") or 0)
    floor = int(seo_block.get("topics_min") or 0)

    seed = pos.get(repo)
    if isinstance(seed, dict) and not seed.get("awaiting_publish"):
        topics = [t for t in (seed.get("search_topics") or []) if _TOPIC_RE.match(str(t))][:20]
        return {
            "description": str(seed.get("seo_description") or "").strip()[:350] or cur_desc,
            "homepage": cur_home or default_home,
            "topics": topics or None,  # None ⇒ leave topics untouched
            "source": "positioning-seed",
        }
    srow = seo_rows.get(repo)
    if isinstance(srow, dict):
        topics = [t for t in (srow.get("topics") or []) if _TOPIC_RE.match(str(t))][:20]
        return {
            "description": str(srow.get("description") or "").strip()[:350] or cur_desc,
            "homepage": str(srow.get("homepage") or "").strip() or cur_home or default_home,
            "topics": topics or None,
            "source": "seo-seed",
        }
    # derivation: fill gaps only.
    want_topics = None
    if n_topics < floor:
        merged = list(dict.fromkeys((row.get("_current_topics") or []) + _derive_topics(row)))[:20]
        want_topics = merged if len(merged) > n_topics else None
    return {
        "description": cur_desc or row.get("_derived_description") or "",
        "homepage": cur_home or (default_home if seo_block.get("homepage") == "required" else cur_home),
        "topics": want_topics,
        "source": "derived",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Repo metadata effector (description/topics/homepage).")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--suggest", action="store_true", help="draft seo-seeds rows for gap repos (print only)")
    args = ap.parse_args(argv)

    gitvs = _module("gitvs", "gitvs.py")
    estate = gitvs.load_estate()
    rows = gitvs._facts_rows()
    if rows is None:
        print("[repo-metadata] no census facts — run `gitvs.py census` first (skip, fail-open)")
        return 0
    pos, seo_rows, default_home = _seeds()
    classes = estate.get("classes") or {}

    plans: list[dict] = []
    for row in rows:
        if row.get("private") or row.get("archived") or row.get("fork"):
            continue
        repo = str(row["full_name"])
        cls = classes.get(gitvs.classify_repo(repo, estate, facts=row) or "") or {}
        seo_block = cls.get("seo")
        if not isinstance(seo_block, dict):
            continue
        gap = (
            (seo_block.get("description") == "required" and not str(row.get("description") or "").strip())
            or (int(row.get("topics_count") or 0) < int(seo_block.get("topics_min") or 0))
            or (seo_block.get("homepage") == "required" and not str(row.get("homepage") or "").strip())
        )
        seeded = repo in pos or repo in seo_rows
        if not gap and not seeded:
            continue
        plans.append({"row": row, "seo": seo_block, "repo": repo})

    if args.suggest:
        print("# draft seo-seeds.yaml rows (curate the copy — this output is never auto-applied):")
        for p in plans:
            if p["repo"] in pos or p["repo"] in seo_rows:
                continue
            row = p["row"]
            row["_derived_description"] = _derive_description(p["repo"])
            topics = _derive_topics(row)
            print(f'  {p["repo"]}:')
            print(f'    description: "{row["_derived_description"][:120]}"')
            print(f"    topics: [{', '.join(topics[:8])}]")
            print("    owner: seo")
            print('    note: "drafted by --suggest; curated by hand"')
        return 0

    # diff desired − observed per gap repo (live re-read before any write — never trust stale facts).
    cap = int(os.environ.get("LIMEN_REPO_METADATA_MAX", "25"))
    armed = bool(args.apply) and os.environ.get("LIMEN_REPO_METADATA_APPLY") == "1"
    mode = "APPLY" if armed else ("apply (DARK — set LIMEN_REPO_METADATA_APPLY=1)" if args.apply else "plan (dry)")
    drift = 0
    written = 0
    lines: list[str] = []
    for p in plans:
        repo, row, seo_block = p["repo"], p["row"], p["seo"]
        live = _current(repo)
        if live is not None:
            row = {**row, "description": live.get("description"), "homepage": live.get("homepage"),
                   "topics_count": len(live.get("topics") or []), "_current_topics": live.get("topics") or [],
                   "language": live.get("language")}
        if not str(row.get("description") or "").strip() and repo not in pos and repo not in seo_rows:
            row["_derived_description"] = _derive_description(repo)
        want = desired_for(row, pos, seo_rows, default_home, seo_block)
        changes: list[str] = []
        if want["description"] and want["description"] != str(row.get("description") or "").strip():
            changes.append("description")
        if want["homepage"] and want["homepage"] != str(row.get("homepage") or "").strip():
            changes.append("homepage")
        cur_topics = set(row.get("_current_topics") or [])
        if want["topics"] is not None and set(want["topics"]) != cur_topics:
            changes.append(f"topics({len(cur_topics)}→{len(want['topics'])})")
        if not changes:
            continue
        drift += 1
        if armed and written < cap:
            ok = True
            edit_args = ["api", "-X", "PATCH", f"/repos/{repo}"]
            patched = False
            if "description" in changes:
                edit_args += ["-f", f"description={want['description']}"]
                patched = True
            if "homepage" in changes:
                edit_args += ["-f", f"homepage={want['homepage']}"]
                patched = True
            if patched:
                ok = _gh(edit_args, timeout=30).returncode == 0
            if any(c.startswith("topics") for c in changes) and want["topics"]:
                targs = ["api", "-X", "PUT", f"/repos/{repo}/topics", "-H", "Accept: application/vnd.github+json"]
                for t in want["topics"]:
                    targs += ["-f", f"names[]={t}"]
                ok = _gh(targs, timeout=30).returncode == 0 and ok
            written += 1
            lines.append(f"   {'✓' if ok else '✗'} {repo} [{want['source']}]: {', '.join(changes)}")
        else:
            held = "" if not armed else " (cap held)" if written >= cap else ""
            lines.append(f"   · {repo} [{want['source']}]: {', '.join(changes)}{held}")

    print(f"[repo-metadata] {mode}: {drift} repo(s) with metadata drift (cap {cap}/run)")
    for ln in lines[:40]:
        print(ln)
    if args.check:
        return 1 if drift else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
