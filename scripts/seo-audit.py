#!/usr/bin/env python3
"""seo-audit.py — the README/SEO standard as a checkable predicate (the portal organ's audit rung).

The public estate is the inbound-traffic surface ("repos are lures"); this makes the lure standard
EXECUTABLE instead of vibes. Each public repo whose class declares an `seo:` block in
institutio/github/estate.yaml is scored against rungs:

  S1 h1            exactly one leading `# ` H1 within the first 5 non-empty lines
  S2 value-prop    first paragraph after the H1 is 80–600 chars (the search snippet)
  S3 badge         ≥1 badge image in the first 15 lines
  S4 quickstart    a Quick start / Getting started / Install / Usage heading
  S5 architecture  an Architecture / How it works / Design heading
  S6 hub-link      a link back into the estate (org hub / homepage / positioning page)
  S7 cta           a contact path (mailto: or a Contact link)
  S8 topics        live topics meet the class floor      (owned by repo-metadata-sync)
  S9 metadata      description + homepage set             (owned by repo-metadata-sync)
  S10 no-price     no currency/price token (the generate-positioning no-price contract)

pass(portal)  ⟺ S1–S7 ∧ S10        pass(minimal) ⟺ S1 ∧ S2 ∧ S4 ∧ S10
S8/S9 are scored for the gap list but never gate a README task — the metadata effector converges them.

  python3 scripts/seo-audit.py --sweep            # score every governed public repo → logs/seo-audit.json
  python3 scripts/seo-audit.py --repo o/r --check # per-repo done-predicate (exit 0 ⟺ pass) — task gate
  python3 scripts/seo-audit.py --check            # estate posture: exit 0 ⟺ no failing repo in the sweep
  python3 scripts/seo-audit.py --doctor           # offline registry parity (seo-seeds.yaml discipline)

Env: LIMEN_OFFLINE (skip live), LIMEN_SEO_TIMEOUT. Fail-open: an unreachable README scores as absent.
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
AUDIT = ROOT / "logs" / "seo-audit.json"
SEO_SEEDS = ROOT / "institutio" / "github" / "seo-seeds.yaml"
POSITIONING_SEEDS = ROOT / "positioning-seeds.json"

sys.path.insert(0, str(SCRIPT_DIR))

_PRICE_RE = re.compile(r"[$€£]|\b\d[\d,]*\s*k\b|/\s*mo\b", re.IGNORECASE)  # generate-positioning contract
_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,34}$")
_BADGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*(?:shields\.io|badge|workflows?)[^)]*\)", re.I)
_QUICKSTART_RE = re.compile(r"^#{2,}\s*(quick\s*start|getting\s+started|install|usage)", re.I | re.M)
_ARCH_RE = re.compile(r"^#{2,}\s*(architecture|how\s+it\s+works|design)", re.I | re.M)
_HUB_RE = re.compile(r"github\.com/organvm|4444j99|\.pages\.dev|docs/positioning/", re.I)
_CTA_RE = re.compile(r"mailto:|^#{2,}\s*contact|\[contact[^\]]*\]\(", re.I | re.M)


def _module(name: str, filename: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def score_readme(text: str | None) -> dict[str, bool]:
    """The pure README half (S1–S7, S10). None text ⇒ every rung false except S10."""
    if not text:
        return {f"S{i}": False for i in (1, 2, 3, 4, 5, 6, 7)} | {"S10": True}
    lines = text.splitlines()
    nonempty = [ln for ln in lines if ln.strip()][:5]
    h1s = [ln for ln in lines if ln.startswith("# ")]
    s1 = len(h1s) == 1 and any(ln.startswith("# ") for ln in nonempty)
    para = ""
    if s1:
        after = text.split(h1s[0], 1)[1]
        for block in re.split(r"\n\s*\n", after):
            block = block.strip()
            if block and not block.startswith(("#", "!", "<", "[!", "```", "|", ">")):
                para = block
                break
    return {
        "S1": s1,
        "S2": 80 <= len(para) <= 600,
        "S3": bool(_BADGE_RE.search("\n".join(lines[:15]))),
        "S4": bool(_QUICKSTART_RE.search(text)),
        "S5": bool(_ARCH_RE.search(text)),
        "S6": bool(_HUB_RE.search(text)),
        "S7": bool(_CTA_RE.search(text)),
        "S10": not _PRICE_RE.search(text),
    }


def score_metadata(row: dict, seo: dict) -> dict[str, bool]:
    """S8/S9 from the census facts against the class floor (the metadata effector's half)."""
    return {
        "S8": (row.get("topics_count") or 0) >= int(seo.get("topics_min") or 0),
        "S9": bool(str(row.get("description") or "").strip())
        and (seo.get("homepage") != "required" or bool(str(row.get("homepage") or "").strip())),
    }


def passes(rungs: dict[str, bool], standard: str) -> bool:
    need = ("S1", "S2", "S4", "S10") if standard == "minimal" else ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S10")
    return all(rungs.get(r, False) for r in need)


def _readme(repo: str) -> str | None:
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return None
    try:
        r = subprocess.run(
            ["gh", "api", f"/repos/{repo}/readme", "--jq", ".content"],
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("LIMEN_SEO_TIMEOUT", "300")) // 10 or 30,
        )
        if r.returncode != 0:
            return None
        return base64.b64decode(r.stdout.strip()).decode("utf-8", errors="replace")
    except Exception:
        return None


def _governed(estate: dict, rows: list[dict], gitvs) -> list[tuple[dict, str, dict]]:
    """(facts_row, standard, seo_block) for every public repo whose class declares seo."""
    classes = estate.get("classes") or {}
    out = []
    for row in rows:
        if row.get("private"):
            continue
        cls = classes.get(gitvs.classify_repo(str(row["full_name"]), estate, facts=row) or "") or {}
        seo = cls.get("seo")
        if isinstance(seo, dict):
            out.append((row, str(seo.get("readme") or "minimal"), seo))
    return out


def cmd_sweep(estate: dict, gitvs) -> int:
    rows = gitvs._facts_rows()
    if rows is None:
        print("[seo-audit] no census facts — run `gitvs.py census` first (skip)")
        return 0
    results: dict[str, dict] = {}
    for row, standard, seo in _governed(estate, rows, gitvs):
        repo = str(row["full_name"])
        rungs = score_readme(_readme(repo)) | score_metadata(row, seo)
        results[repo] = {"standard": standard, "rungs": rungs, "pass": passes(rungs, standard)}
    failing = sorted(r for r, v in results.items() if not v["pass"])
    body = {
        "schema": "limen.seo_audit.v1",
        "audited": len(results),
        "passing": len(results) - len(failing),
        "failing": failing,
        "repos": dict(sorted(results.items())),
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    print(f"[seo-audit] swept {len(results)} public repos: {body['passing']} pass, {len(failing)} fail → {AUDIT.relative_to(ROOT)}")
    return 0


def cmd_check_repo(repo: str, estate: dict, gitvs) -> int:
    rows = gitvs._facts_rows() or []
    row = next((r for r in rows if r.get("full_name") == repo), None)
    if row is None:
        print(f"[seo-audit] {repo}: not in the census facts — run census first")
        return 1
    governed = {str(r["full_name"]): (s, seo) for r, s, seo in _governed(estate, rows, gitvs)}
    if repo not in governed:
        print(f"[seo-audit] {repo}: class declares no seo block — standard not demanded (pass)")
        return 0
    standard, seo = governed[repo]
    rungs = score_readme(_readme(repo)) | score_metadata(row, seo)
    ok = passes(rungs, standard)
    misses = sorted(k for k, v in rungs.items() if not v)
    print(f"[seo-audit] {repo} [{standard}]: {'PASS' if ok else 'FAIL'}" + (f" — missing {', '.join(misses)}" if misses else ""))
    return 0 if ok else 1


def cmd_check(estate: dict) -> int:
    try:
        body = json.loads(AUDIT.read_text(encoding="utf-8"))
    except Exception:
        print("[seo-audit] no sweep artifact yet — run --sweep first (skip)")
        return 0
    failing = body.get("failing") or []
    if failing:
        print(f"[seo-audit] {len(failing)}/{body.get('audited')} public repos below their README standard")
        for r in failing[:10]:
            print(f"   {r}")
        return 1
    print(f"[seo-audit] all {body.get('audited')} governed public repos meet their README standard")
    return 0


def cmd_doctor() -> int:
    """Offline registry parity for the seo-seeds overlay (the check-gates analogue)."""
    fails: list[str] = []
    try:
        seeds = yaml.safe_load(SEO_SEEDS.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        print("[seo-audit] doctor: seo-seeds.yaml absent — derivation-only mode (ok)")
        return 0
    except Exception as e:
        print(f"[seo-audit] doctor: seo-seeds.yaml unparseable ({e})")
        return 1
    if "schema_version" not in seeds:
        fails.append("seo-seeds: missing schema_version")
    try:
        positioned = set((json.loads(POSITIONING_SEEDS.read_text()).get("repos") or {}).keys())
    except Exception:
        positioned = set()
    for repo, row in (seeds.get("repos") or {}).items():
        where = f"seo-seed '{repo}'"
        if repo in positioned:
            fails.append(f"{where}: also in positioning-seeds.json — the positioning seed wins; remove this row")
        if not isinstance(row, dict):
            fails.append(f"{where}: not a mapping")
            continue
        for field in ("owner", "note"):
            if field not in row:
                fails.append(f"{where}: missing '{field}'")
        desc = str(row.get("description") or "")
        if len(desc) > 350:
            fails.append(f"{where}: description >350 chars")
        if _PRICE_RE.search(desc):
            fails.append(f"{where}: description carries a price/currency token")
        topics = row.get("topics") or []
        if len(topics) > 20:
            fails.append(f"{where}: >20 topics")
        for t in topics:
            if not _TOPIC_RE.match(str(t)):
                fails.append(f"{where}: invalid topic '{t}'")
    if fails:
        print(f"[seo-audit] doctor: {len(fails)} registry defect(s):")
        for f in fails:
            print(f"   {f}")
        return 1
    print("[seo-audit] doctor: seo-seeds registry parity green")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="README/SEO standard as a predicate (portal-v1).")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--repo")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--doctor", action="store_true")
    args = ap.parse_args(argv)

    if args.doctor:
        return cmd_doctor()
    gitvs = _module("gitvs", "gitvs.py")
    estate = gitvs.load_estate()
    if args.sweep:
        return cmd_sweep(estate, gitvs)
    if args.repo:
        return cmd_check_repo(args.repo, estate, gitvs)
    if args.check:
        return cmd_check(estate)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
