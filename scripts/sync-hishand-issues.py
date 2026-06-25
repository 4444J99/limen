#!/usr/bin/env python3
"""sync-hishand-issues.py — keep his-hand-levers.json and the GitHub graph in lockstep.

The charter's invariant is that a his-hand lever NEVER hangs in a file only Claude
reads — it must be OWNED and ASSIGNED in the durable graph. `his-hand-levers.json`
makes a lever owned; this organ makes it *assigned*: every lever gets exactly one
open, individually-closeable `needs-human` GitHub issue, and the lever is stamped
with that issue number so the registry and the graph can never silently diverge.

Identity is by an HTML marker in the issue body — `<!-- lever:L-XXX -->` — never by
title, so a lever's wording can change without orphaning or duplicating its issue.

Idempotent. DRY-RUN by default; `--apply` mutates GitHub + the JSON. It NEVER reopens
or closes an issue on its own — closing a needs-human issue is the human's signal that
the lever is pulled, and this organ respects that (a closed issue stays closed; its
number stays stamped so the predicate can see the lever was discharged).

  python3 scripts/sync-hishand-issues.py            # show the plan, touch nothing
  python3 scripts/sync-hishand-issues.py --apply     # create missing issues, stamp JSON

PII firewall (memory: health-pii-in-generator-code): the registry publishes, so this
script copies lever text verbatim into public issues — it adds NOTHING of its own about
him. The levers are already shape-scanned by no-tasks-on-me.sh before they can land.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = Path(__import__("os").environ.get("LIMEN_HIS_HAND_LEVERS", ROOT / "his-hand-levers.json"))
LABEL = "needs-human"
MARKER_RE = re.compile(r"<!--\s*lever:(L-[A-Z0-9-]+)\s*-->")


def sh(args: list[str], check: bool = True, input_text: str | None = None) -> str:
    r = subprocess.run(args, capture_output=True, text=True, input=input_text)
    if check and r.returncode != 0:
        sys.stderr.write(f"$ {' '.join(args)}\n{r.stdout}{r.stderr}\n")
        raise SystemExit(f"command failed ({r.returncode})")
    return r.stdout.strip()


def title_for(lever: dict) -> str:
    """A concise, stable-ish title. Body carries the full label."""
    label = " ".join(str(lever.get("label", "")).split())
    # first clause up to a sentence/colon boundary, capped.
    head = re.split(r"[:.]\s", label, maxsplit=1)[0]
    if len(head) > 72:
        head = head[:69].rstrip() + "…"
    return f"needs-human ({lever['id']}): {head}" if head else f"needs-human ({lever['id']})"


def body_for(lever: dict) -> str:
    lid = lever["id"]
    out = [
        f"**Owner:** Anthony (human-gated lever `{lid}`). Surfaced once, never nagged, "
        "never auto-pulled. This issue is the lever's permanent, individually-closeable "
        "home in the graph — the registry `his-hand-levers.json` is its source of truth.",
        "",
        str(lever.get("label", "")).strip(),
        "",
        "### What it unlocks",
        str(lever.get("unlocks", "—")).strip(),
        "",
        "### Cost",
        str(lever.get("cost", "—")).strip(),
    ]
    if lever.get("gate"):
        out += ["", "### Gate", str(lever["gate"]).strip()]
    steps = lever.get("steps")
    if isinstance(steps, list) and steps:
        out += ["", "### Cheapest path"] + [f"- {str(s).strip()}" for s in steps]
    out += [
        "",
        "### Source",
        f"`{lever.get('source_task', '—')}` · registry: `his-hand-levers.json` → lever `{lid}`",
        "",
        "*Close this issue when the action is done — the lever is pulled then.*",
        "",
        f"<!-- lever:{lid} -->",
    ]
    return "\n".join(out)


def existing_issues() -> dict[str, dict]:
    """marker lever-id -> {number, state, body} for every needs-human issue.

    Uses the REST API, not `gh issue list --label` — the latter routes through
    GitHub's search index, which lags by minutes for freshly-created issues and
    would make this organ non-idempotent right after it runs. REST is immediate
    and returns the FULL body (the marker is the last line, so a truncated body
    preview would silently drop it).
    """
    raw = sh(["gh", "api", "--paginate",
              f"repos/{repo_slug()}/issues?labels={LABEL}&state=all&per_page=100"])
    # --paginate concatenates JSON arrays; normalise to one list.
    issues: list = []
    for chunk in re.findall(r"\[.*?\]\s*(?=\[|\Z)", raw, re.S) or [raw]:
        try:
            issues.extend(json.loads(chunk))
        except json.JSONDecodeError:
            pass
    out: dict[str, dict] = {}
    for it in issues:
        if "pull_request" in it:  # REST returns PRs as issues; skip them
            continue
        m = MARKER_RE.search(it.get("body") or "")
        if m:
            out[m.group(1)] = {"number": it["number"], "state": it["state"].upper(),
                               "body": it.get("body") or ""}
    return out


def repo_slug() -> str:
    return sh(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])


def create_issue(lever: dict) -> int:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body_for(lever))
        path = f.name
    url = sh(["gh", "issue", "create", "--label", LABEL,
              "--title", title_for(lever), "--body-file", path])
    return int(url.rstrip("/").split("/")[-1])


def update_issue(num: int, lever: dict) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body_for(lever))
        path = f.name
    sh(["gh", "issue", "edit", str(num), "--title", title_for(lever), "--body-file", path])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="mutate GitHub + the JSON (default: dry-run)")
    ap.add_argument("--update-bodies", action="store_true",
                    help="also rewrite the body/title of existing open issues to match the lever")
    args = ap.parse_args()

    data = json.loads(REGISTRY.read_text())
    levers = data.get("levers", [])
    if not levers:
        raise SystemExit("registry has no levers")

    by_marker = existing_issues()
    by_number = {v["number"]: v for v in by_marker.values()}
    plan_create, plan_link, plan_update, already = [], [], [], []
    dirty = False

    for lev in levers:
        lid = lev["id"]
        stamped = lev.get("issue")
        # Primary key: the registry's stamped issue number (durable, offline,
        # immune to search-index lag). Marker-scan is recovery for unstamped levers.
        found = by_number.get(stamped) if isinstance(stamped, int) else by_marker.get(lid)
        if found:
            num = found["number"]
            if lev.get("issue") != num:
                plan_link.append((lid, num))
                if args.apply:
                    lev["issue"] = num
                    dirty = True
            else:
                already.append((lid, num, found["state"]))
            if args.update_bodies and found["state"] == "OPEN":
                plan_update.append((lid, num))
                if args.apply:
                    update_issue(num, lev)
        else:
            if args.apply:
                num = create_issue(lev)
                lev["issue"] = num
                dirty = True
                plan_create.append((lid, num))
            else:
                plan_create.append((lid, None))

    if args.apply and dirty:
        REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    verb = "CREATED" if args.apply else "would create"
    print(f"== sync-hishand-issues ({'APPLY' if args.apply else 'DRY-RUN'}) ==")
    print(f"registry: {REGISTRY}  ({len(levers)} levers)")
    for lid, num in plan_create:
        print(f"  {verb:13} {lid}" + (f"  -> #{num}" if num else ""))
    for lid, num in plan_link:
        print(f"  {'LINKED' if args.apply else 'would link':13} {lid}  -> existing #{num}")
    for lid, num in plan_update:
        print(f"  {'UPDATED' if args.apply else 'would update':13} {lid}  -> #{num}")
    for lid, num, st in already:
        print(f"  {'in-sync':13} {lid}  -> #{num} ({st})")
    missing = [lid for lid, n in plan_create if n is None]
    if missing and not args.apply:
        print(f"\n{len(missing)} lever(s) have no owned issue. Re-run with --apply to assign them.")
    elif args.apply:
        print(f"\nstamped {sum(1 for _ in plan_create)+len(plan_link)} lever->issue link(s) into the registry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
