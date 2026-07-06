#!/usr/bin/env python3
"""merge-ready.py — turn the merge gate into ONE go/no-go.

The fleet BUILDS faster than it SHIPS: merge-ready PRs pile up because merging is outward +
irreversible, so the classifier holds the whole batch behind a single human gate. But "open the merge
gate" is currently a *hunt* — nobody can see, at a glance, which PRs are actually clean and which
matter most. This builds that view.

READ-ONLY. It reuses merge-drain.py's EXACT assessment (`assess`: READY / CI-RED / CI-PENDING /
CONFLICT / TRIVIAL / SKIP) so the surface can never disagree with what the merge organ would actually
do — then ranks the READY set REVENUE-FIRST (revenue-ladder.json rank, then value-repos membership) and
emits a single ranked list to docs/MERGE-READY.md + logs/merge-ready.json. It NEVER merges anything;
the gate stays his. The whole point: when he says "open the merge gate," this is the list it acts on.

Derive-don't-pin: ranks come from revenue-ladder.json + value-repos.json at run time, never hardcoded.
Fail-open: any unreadable input yields an empty section, never a crash; gh unavailable -> empty surface.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
DOCS = ROOT / "docs"


def _load_merge_drain():
    """Load the sibling merge-drain.py (hyphenated -> can't `import`) so we reuse its EXACT
    open_prs/assess classifier instead of forking a second, drifting copy."""
    path = Path(__file__).resolve().parent / "merge-drain.py"
    spec = importlib.util.spec_from_file_location("merge_drain", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ladder_ranks() -> dict[str, int]:
    """repo -> revenue rank (lower = closer to a dollar). {} on any error."""
    try:
        data = json.loads((ROOT / "revenue-ladder.json").read_text())
    except (OSError, ValueError):
        return {}
    return {p["repo"]: p.get("rank", 99)
            for p in (data.get("products") or []) if isinstance(p, dict) and p.get("repo")}


def _value_repos() -> set[str]:
    try:
        data = json.loads((ROOT / "value-repos.json").read_text())
    except (OSError, ValueError):
        return set()
    if isinstance(data, dict):
        repos = data.get("repos") or []
    elif isinstance(data, list):
        repos = data
    else:
        repos = []
    return {str(repo) for repo in repos if repo}


def _open_prs(md, scan: int) -> list[tuple[str, int]]:
    if hasattr(md, "enumerate_open_prs"):
        return md.enumerate_open_prs(md.OWNERS, md.gh, max_total=scan, want_url=False)
    if hasattr(md, "open_prs"):
        return md.open_prs(scan)
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", type=int, default=80, help="max open PRs to assess")
    args = ap.parse_args(argv)

    md = _load_merge_drain()
    ranks = _ladder_ranks()
    value = _value_repos()

    prs = _open_prs(md, args.scan)
    rows = []
    if prs:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(md.assess, prs))

    buckets: dict[str, list] = {}
    for repo, num, status in rows:
        buckets.setdefault(status, []).append((repo, num))

    def rank_key(item):
        repo, num = item
        return (ranks.get(repo, 500), 0 if repo in value else 1, repo, num)

    ready = sorted(buckets.get("READY", []), key=rank_key)

    surface = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scanned": len(prs),
        "counts": {k: len(v) for k, v in sorted(buckets.items())},
        "ready": [
            {"ref": f"{repo}#{num}", "repo": repo, "number": num,
             "revenue_rank": ranks.get(repo), "value_repo": repo in value}
            for repo, num in ready
        ],
        "blocked": {
            k: [f"{r}#{n}" for r, n in sorted(buckets.get(k, []), key=rank_key)]
            for k in ("CONFLICT", "CI-RED", "CI-PENDING", "TRIVIAL", "ERR")
            if buckets.get(k)
        },
    }

    # logs/merge-ready.json (machine) -------------------------------------------------------------
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        (LOGS / "merge-ready.json").write_text(json.dumps(surface, indent=2))
    except OSError:
        pass

    # docs/MERGE-READY.md (his one go/no-go) ------------------------------------------------------
    c = surface["counts"]
    lines = [
        f"# Merge-ready — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Scanned **{surface['scanned']}** open PRs (authored by you, across `organvm` + `4444J99`). "
        f"**{c.get('READY', 0)} are CLEAN** (mergeable + CI-green + non-trivial) and ranked revenue-first below.",
        "",
        "> This is the **single go/no-go**: say *\"open the merge gate\"* and `merge-drain.py` squash-merges "
        "exactly this READY set (revenue-first), deletes the branches, and never force-merges. "
        "Nothing here is merged by generating this list — the gate is yours.",
        "",
        "## ✅ READY — clean, ranked revenue-first",
        "",
    ]
    if ready:
        lines += ["| # | PR | revenue rank | value-repo |", "|---|---|---|---|"]
        for i, (repo, num) in enumerate(ready, 1):
            rr = ranks.get(repo)
            lines.append(f"| {i} | `{repo}#{num}` | {rr if rr is not None else '—'} | "
                         f"{'✓' if repo in value else ''} |")
    else:
        lines.append("_No clean-ready PRs in this scan._")

    lines += ["", "## ⏳ Blocked (not yours to fix — the fleet heals these)", ""]
    label = {"CONFLICT": "merge conflict (rebase needed)", "CI-RED": "CI failing",
             "CI-PENDING": "CI still running", "TRIVIAL": "no-op/reformat (value gate refuses)",
             "ERR": "assessment error"}
    for k in ("CONFLICT", "CI-RED", "CI-PENDING", "TRIVIAL", "ERR"):
        refs = surface["blocked"].get(k)
        if refs:
            shown = ", ".join(f"`{r}`" for r in refs[:12])
            more = f" … (+{len(refs) - 12} more)" if len(refs) > 12 else ""
            lines.append(f"- **{label[k]}** ({len(refs)}): {shown}{more}")
    if not surface["blocked"]:
        lines.append("_None._")
    lines += ["", "---", "*Generated read-only by `scripts/merge-ready.py` — reuses `merge-drain.py`'s "
              "classifier. Re-run any time. Nothing merged without your word.*", ""]

    try:
        DOCS.mkdir(parents=True, exist_ok=True)
        (DOCS / "MERGE-READY.md").write_text("\n".join(lines))
    except OSError:
        pass

    print(f"merge-ready: scanned {surface['scanned']} -> READY {c.get('READY', 0)} "
          f"(conflict {c.get('CONFLICT', 0)}, ci-red {c.get('CI-RED', 0)}, "
          f"ci-pending {c.get('CI-PENDING', 0)}, trivial {c.get('TRIVIAL', 0)}) "
          f"-> docs/MERGE-READY.md + logs/merge-ready.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
