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

# The aggregate his-hand Wall — one pinned, machine-maintained index of EVERY lever, mirroring the
# credential Wall (#320, scripts/credential-wall.py) for the rest of the human-gated estate. Identity
# is its own marker so the per-lever sync never mistakes it for a lever.
WALL_MARKER = "<!-- wall:hishand -->"
WALL_TITLE = "🧱 The Wall — everything that hangs on you (his-hand levers)"


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


_SLUG: str | None = None


def repo_slug() -> str:
    global _SLUG
    if _SLUG is None:  # memoised — issue_by_number() calls this per unmatched-stamp lever
        _SLUG = sh(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
    return _SLUG


def issue_by_number(num: int) -> dict | None:
    """A single issue by number (REST), or None if it's a PR or absent. Recognises a stamped
    pointer that predates our marker/label — so a VALID pointer is never re-minted as a duplicate.
    (The #892/#827 bug: a real issue lacking the `<!-- lever:… -->` marker was invisible to the
    marker-scan, so every --apply re-minted a fresh marked issue and repointed the lever at it.)"""
    raw = sh(["gh", "api", f"repos/{repo_slug()}/issues/{num}"], check=False)
    try:
        it = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(it, dict) or "number" not in it or "pull_request" in it:
        return None
    return {"number": it["number"], "state": (it.get("state") or "open").upper(),
            "body": it.get("body") or ""}


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


def _head(text: str, cap: int = 90) -> str:
    """First clause of a lever label, collapsed + capped — for the Wall table."""
    label = " ".join(str(text).split())
    head = re.split(r"[:.]\s", label, maxsplit=1)[0]
    return head[: cap - 1].rstrip() + "…" if len(head) > cap else head


def wall_body(levers: list[dict]) -> str:
    """The aggregate his-hand Wall body — every lever, machine-generated from the registry."""
    out = [
        "**This is the single pinned index of everything that hangs on Anthony.** Every row is a "
        "lever only he can pull; each links its own individually-closeable issue. Close an issue to "
        "pull that lever — nothing here is ever auto-pulled or nagged. The credential/secret/login/"
        "env subset has its own machine-generated Wall (#320); this Wall covers the rest.",
        "",
        "_Source of truth: [`his-hand-levers.json`](https://github.com/organvm/limen/blob/main/his-hand-levers.json). "
        "Regenerate: `python3 scripts/sync-hishand-issues.py --wall --apply`. If this table and the "
        "registry disagree, the registry wins. Live filter: "
        "<https://github.com/organvm/limen/labels/needs-human>._",
        "",
        "| Lever | What it unlocks | Cost | Issue |",
        "|---|---|---|---|",
    ]
    for lev in levers:
        lid = lev.get("id", "—")
        unlocks = _head(lev.get("unlocks", "—"), 70) or "—"
        cost = _head(lev.get("cost", "—"), 60) or "—"
        num = lev.get("issue")
        link = f"#{num}" if isinstance(num, int) else "—"
        out.append(f"| `{lid}` — {_head(lev.get('label', ''), 70)} | {unlocks} | {cost} | {link} |")
    out += [
        "",
        f"_{len(levers)} levers. Pinned alongside the credential Wall (#320). "
        "Surfaced once, here — never recited in a chat._",
        "",
        WALL_MARKER,
    ]
    return "\n".join(out)


def find_marked(marker: str) -> int | None:
    """Issue number whose body carries `marker`, or None. Scans needs-human issues via REST."""
    raw = sh(["gh", "api", "--paginate",
              f"repos/{repo_slug()}/issues?labels={LABEL}&state=all&per_page=100"])
    issues: list = []
    for chunk in re.findall(r"\[.*?\]\s*(?=\[|\Z)", raw, re.S) or [raw]:
        try:
            issues.extend(json.loads(chunk))
        except json.JSONDecodeError:
            pass
    for it in issues:
        if "pull_request" in it:
            continue
        if marker in (it.get("body") or ""):
            return it["number"]
    return None


def sync_wall(levers: list[dict], apply: bool) -> int:
    body = wall_body(levers)
    num = find_marked(WALL_MARKER)
    if not apply:
        where = f"existing #{num}" if num else "a NEW pinned issue"
        print(f"== his-hand Wall (DRY-RUN) ==\nwould write {len(levers)} levers into {where}\n")
        print(body)
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body)
        path = f.name
    if num:
        sh(["gh", "issue", "edit", str(num), "--title", WALL_TITLE, "--body-file", path])
    else:
        url = sh(["gh", "issue", "create", "--label", LABEL, "--title", WALL_TITLE, "--body-file", path])
        num = int(url.rstrip("/").split("/")[-1])
    # Keep it pinned; pinning an already-pinned issue errors harmlessly → tolerate.
    subprocess.run(["gh", "issue", "pin", str(num)], capture_output=True, text=True)
    print(f"✓ his-hand Wall synced + pinned → issue #{num} ({len(levers)} levers)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="mutate GitHub + the JSON (default: dry-run)")
    ap.add_argument("--update-bodies", action="store_true",
                    help="also rewrite the body/title of existing open issues to match the lever")
    ap.add_argument("--wall", action="store_true",
                    help="generate/refresh the single pinned aggregate his-hand Wall issue")
    args = ap.parse_args()

    data = json.loads(REGISTRY.read_text())
    levers = data.get("levers", [])
    if not levers:
        raise SystemExit("registry has no levers")

    if args.wall:
        return sync_wall(levers, args.apply)

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
        if not found and isinstance(stamped, int):
            # Stamped at a real issue that lacks our marker (manual/older, e.g. #892/#827):
            # still a valid home — recognise it instead of minting a duplicate.
            found = issue_by_number(stamped)
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
