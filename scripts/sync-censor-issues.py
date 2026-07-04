#!/usr/bin/env python3
"""sync-censor-issues.py — mirror live censor residuals into the GitHub graph.

The insights→actions loop produces its findings as *censor residuals*
(`logs/censor-residual.json`, gitignored runtime state) — which made the system's
own open work invisible on GitHub: a correction PR like #637 had no issue to
arrive as and nothing to close. This organ gives every live `warning` residual
exactly one open, individually-closeable `censor`-labelled issue, and closes that
issue (with a citation) the moment the residual clears from the lineage — so
insight→correction work arrives as an issue and leaves as a PR that cites it.

Identity is by an HTML marker in the issue body — `<!-- censor:<residual-id> -->`
— never by title, so wording can change without orphaning or duplicating.

Semantics (deliberately asymmetric to sync-hishand-issues.py):
  • censor issues are SYSTEM-owned → this organ both opens AND closes them;
  • a HUMAN close is a veto — respected forever, never reopened;
  • `info` / resolved residuals never open issues (they only close old ones);
  • creates are capped per pass (the beat converges over passes, never floods).

Idempotent. DRY-RUN by default; `--apply` mutates GitHub and stamps
`logs/censor-issues.json` (organs must stamp — gauges lie). Ships observable-
before-autonomous per the censor constitution: the beat runs it dry until
LIMEN_CENSOR_ISSUES_APPLY=1 arms it (same pattern as LIMEN_CENSOR_APPLY).

PII firewall (memory: health-pii-in-generator-code): residual title/detail are
copied verbatim into public issues and this organ adds NOTHING of its own about
him. Residuals describe agent behaviour distilled from the insights lineage —
the same content class CLAUDE.md already publishes as standing corrections.

  python3 scripts/sync-censor-issues.py            # show the plan, touch nothing
  python3 scripts/sync-censor-issues.py --apply    # open/close issues, stamp the log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
RESIDUALS = ROOT / "logs" / "censor-residual.json"
PRECEDENTS = ROOT / "censor" / "precedents.jsonl"
STAMP = ROOT / "logs" / "censor-issues.json"
LABEL = "censor"
MARKER_RE = re.compile(r"<!--\s*censor:([A-Za-z0-9._-]+)\s*-->")
CAP_DEFAULT = 8


def sh(args: list[str], check: bool = True) -> str:
    r = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    if check and r.returncode != 0:
        sys.stderr.write(f"$ {' '.join(args)}\n{r.stdout}{r.stderr}\n")
        raise SystemExit(f"command failed ({r.returncode})")
    return r.stdout.strip()


# ─── pure core (tested in scripts/test_sync_censor_issues.py) ─────────────────

def plan(residuals: list[dict], existing: dict[str, dict], cap: int = CAP_DEFAULT) -> dict:
    """Decide creates/closes from the residual file vs the marked issues on GitHub.

    `existing`: residual-id -> {"number": int, "state": "OPEN"|"CLOSED"}.
    Only `warning` residuals deserve an open issue; anything marked on GitHub
    whose residual is gone or no longer a warning gets closed. A CLOSED issue
    whose residual still warns is a human veto — left closed, reported only.
    """
    warn = {r["id"]: r for r in residuals if r.get("severity") == "warning" and r.get("id")}
    creates = [rid for rid in warn if rid not in existing]
    keeps = sorted((rid, f["number"]) for rid, f in existing.items()
                   if f["state"] == "OPEN" and rid in warn)
    closes = sorted((rid, f["number"]) for rid, f in existing.items()
                    if f["state"] == "OPEN" and rid not in warn)
    vetoed = sorted((rid, f["number"]) for rid, f in existing.items()
                    if f["state"] == "CLOSED" and rid in warn)
    return {"create": creates[:cap], "deferred": creates[cap:],
            "close": closes, "keep": keeps, "vetoed": vetoed}


def precedent_for(residual: dict, precedents: list[dict]) -> dict | None:
    """The settled case-law record whose subject this residual carries, if any.

    Drift residual titles embed the friction label verbatim ("Recurring friction
    across N insights reports: <label>"); precedent subjects ARE those labels.
    """
    title = str(residual.get("title", ""))
    for pc in precedents:
        if (pc.get("type") == "recurring_friction"
                and pc.get("outcome") in ("good", "applied-ok")
                and pc.get("subject") and pc["subject"] in title):
            return pc
    return None


# ─── GitHub I/O (same REST pattern as sync-hishand-issues.py) ─────────────────

def repo_slug() -> str:
    return sh(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])


def existing_issues() -> dict[str, dict]:
    """marker residual-id -> {number, state} for every censor-labelled issue.

    REST, not `gh issue list` — the search index lags freshly-created issues by
    minutes, which would make this organ non-idempotent right after it runs.
    """
    raw = sh(["gh", "api", "--paginate",
              f"repos/{repo_slug()}/issues?labels={LABEL}&state=all&per_page=100"])
    issues: list = []
    for chunk in re.findall(r"\[.*?\]\s*(?=\[|\Z)", raw, re.S) or [raw]:
        try:
            issues.extend(json.loads(chunk))
        except json.JSONDecodeError:
            pass
    out: dict[str, dict] = {}
    for it in issues:
        if "pull_request" in it:
            continue
        m = MARKER_RE.search(it.get("body") or "")
        if m:
            out[m.group(1)] = {"number": it["number"], "state": it["state"].upper()}
    return out


def ensure_label() -> None:
    subprocess.run(["gh", "label", "create", LABEL, "--color", "5319e7",
                    "--description", "censor residual — auto-opened/closed by sync-censor-issues.py"],
                   capture_output=True, text=True, cwd=ROOT)  # exists already → harmless error


def title_for(residual: dict) -> str:
    head = " ".join(str(residual.get("title", "")).split()) or residual["id"]
    if len(head) > 110:
        head = head[:107].rstrip() + "…"
    return f"censor: {head}"


def body_for(residual: dict, precedent: dict | None) -> str:
    rid = residual["id"]
    out = [
        "**Owner:** the censor (limen's insights→actions institution). This issue is the",
        "public, individually-closeable home of a live censor residual — auto-opened by",
        "`scripts/sync-censor-issues.py`, auto-closed the moment the residual clears from",
        "`logs/censor-residual.json` (the beat regenerates that file from the insights",
        "lineage). Closing it by hand is a veto: respected forever, never reopened.",
        "",
        str(residual.get("detail", "")).strip(),
    ]
    if precedent:
        out += [
            "",
            "### Codified as case law",
            f"`{precedent.get('id', '?')}` — the standing correction is already shipped "
            f"({precedent.get('action', 'see censor/precedents.jsonl')}). This issue tracks the "
            "**empirical close**: the friction aging out of a future /insights report's drift.",
        ]
    out += [
        "",
        "### Source",
        f"`{residual.get('source', '—')}` · severity `{residual.get('severity', '—')}` · "
        f"residual `{rid}` · suggested: {str(residual.get('suggested_action', '—')).strip()}",
        "",
        f"<!-- censor:{rid} -->",
    ]
    return "\n".join(out)


def create_issue(residual: dict, precedent: dict | None) -> int:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body_for(residual, precedent))
        path = f.name
    url = sh(["gh", "issue", "create", "--label", LABEL,
              "--title", title_for(residual), "--body-file", path])
    return int(url.rstrip("/").split("/")[-1])


def close_issue(num: int, rid: str) -> None:
    sh(["gh", "issue", "close", str(num), "--comment",
        f"Residual `{rid}` has cleared from `logs/censor-residual.json` — the lineage no longer "
        "carries it as a live warning. Closed by `scripts/sync-censor-issues.py`."])


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="mutate GitHub + stamp (default: dry-run)")
    ap.add_argument("--cap", type=int, default=CAP_DEFAULT, help="max issue creations per pass")
    args = ap.parse_args()

    if not RESIDUALS.exists():
        print(f"censor-issues: no residual file at {RESIDUALS} — nothing to mirror")
        return 0
    residuals = json.loads(RESIDUALS.read_text())
    precedents = _load_jsonl(PRECEDENTS)
    by_id = {r.get("id"): r for r in residuals if r.get("id")}

    if args.apply:
        ensure_label()
    existing = existing_issues()
    p = plan(residuals, existing, cap=args.cap)

    created, closed = [], []
    for rid in p["create"]:
        if args.apply:
            num = create_issue(by_id[rid], precedent_for(by_id[rid], precedents))
            created.append((rid, num))
    for rid, num in p["close"]:
        if args.apply:
            close_issue(num, rid)
            closed.append((rid, num))

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"== sync-censor-issues ({mode}) ==  residuals: {RESIDUALS}")
    for rid in p["create"]:
        num = dict(created).get(rid)
        print(f"  {'OPENED' if num else 'would open':11} {rid}" + (f"  -> #{num}" if num else ""))
    for rid, num in p["close"]:
        print(f"  {'CLOSED' if args.apply else 'would close':11} {rid}  -> #{num}")
    for rid, num in p["keep"]:
        print(f"  {'in-sync':11} {rid}  -> #{num} (OPEN)")
    for rid, num in p["vetoed"]:
        print(f"  {'vetoed':11} {rid}  -> #{num} (human-closed; respected)")
    if p["deferred"]:
        print(f"  {len(p['deferred'])} create(s) deferred past cap {args.cap} — next pass converges")

    if args.apply:
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "created": [n for _, n in created], "closed": [n for _, n in closed],
            "open_after": len(p["keep"]) + len(created), "vetoed": len(p["vetoed"]),
            "deferred": len(p["deferred"]),
        }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
