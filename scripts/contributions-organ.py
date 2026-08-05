#!/usr/bin/env python3
"""contributions-organ.py — SPECVLVM, the contributions mirror (the OSPO organ's face).

Doctrine: we contribute OUTWARD to study other projects' wiring and improve INWARD; community
standing and name recognition are byproducts of genuine value, never the objective. This is the
public proof mirror PLAN-06 owner packet 04 left unowned — limen is the named owner surface
(docs/current-session-fanout/PLAN-06-contrib-mirror.md). It consumes hub-ledger outputs ONLY
(never raw sessions or private archaeology), renders contribution outcomes as proof categories
(merged / open / no-PR / closed / protocol-due / post-close), and redacts local paths and private
notes before anything touches the surface.

Four limbs, one render:
  MIRROR    — the proof surface from hub-ledger outputs (the original face).
  LIFECYCLE — the executable audit of organs/contributions/LIFECYCLE.md: derives protocol-due
              (open PRs stale past LIMEN_CONTRIB_STALE_DAYS, measured against the SOURCE stamp so
              renders stay deterministic) and lifecycle DEBT (terminal PRs whose contrib--*
              workspace is reap-owed: archive + fork settle + ledger closeout).
  ESTATE    — verifies organs/contributions/ESTATE.yaml, the certified register of every script/
              protocol/rule/memory/log/session/plan of the practice; a registered local artifact
              gone absent surfaces as DRIFT.
  SCOUT     — the AUTOPOIETIC limb: looks INWARD (walks our own workspace dependency manifests)
              and derives the OUTWARD pool — the upstreams we already depend on most that we have
              never engaged (organs/contributions/opportunities.json + the pool section of the
              mirror). The organ makes its own next work; the human hand enters only at the send.

Offline on the beat: reads the local hub checkout (LIMEN_CONTRIB_LEDGER) or the committed cache;
a `gh api` cache refresh runs ONLY with --refresh or LIMEN_CONTRIB_REFRESH=1. When every source is
absent it renders its own staleness receipt instead of pretending — an honest mirror shows its
dust — and still exits 0 (fail-open, never gates the beat). By DEFAULT the organ sends nothing: no
comments, bumps, PRs, or posts. Its one outward EFFECTOR (--bump) is DARK unless deliberately armed
(LIMEN_CONTRIB_BUMP=1 or --arm); armed, it fires exactly ONE reversible bump comment at a time on
the oldest protocol-due PR — never a batch. Arming an outward send stays the human's decision.

  python3 scripts/contributions-organ.py            # render MIRROR.md + opportunities.json + logs/contributions.json
  python3 scripts/contributions-organ.py --refresh  # also refresh the ledger cache from GitHub (read-only API)
  python3 scripts/contributions-organ.py --check    # predicate: committed mirror matches a fresh render (exit 0 <=> current)
  python3 scripts/contributions-organ.py --bump     # DARK preview: the one oldest protocol-due bump it WOULD fire
  python3 scripts/contributions-organ.py --bump --arm  # fire that one reversible bump comment (or LIMEN_CONTRIB_BUMP=1)

The mirror body is deterministic (stamped from source metadata, not the clock), so re-runs against
unchanged sources are byte-identical — the idempotent fixed point the closeout discipline demands.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
HUB_LEDGER = Path(os.path.expanduser(os.environ.get("LIMEN_CONTRIB_LEDGER", "~/Workspace/organvm/contrib/LEDGER.yaml")))
HUB_REPO = os.environ.get("LIMEN_CONTRIB_HUB_REPO", "organvm/contrib")
BACKFLOW = Path(
    os.path.expanduser(
        os.environ.get(
            "LIMEN_BACKFLOW_MANIFEST", "~/Workspace/organvm-corpvs-testamentvm/data/atoms/backflow-manifest.yaml"
        )
    )
)
STALE_DAYS = int(os.environ.get("LIMEN_CONTRIB_STALE_DAYS", "14"))
SCOUT_ON = os.environ.get("LIMEN_CONTRIB_SCOUT", "1") == "1"
SCOUT_CAP = int(os.environ.get("LIMEN_CONTRIB_SCOUT_CAP", "12"))
ORGAN_HOME = ROOT / "organs" / "contributions"
CACHE = ORGAN_HOME / "ledger-cache.json"
MIRROR = ORGAN_HOME / "MIRROR.md"
ESTATE = ORGAN_HOME / "ESTATE.yaml"
OPPORTUNITIES = ORGAN_HOME / "opportunities.json"
SIGNAL = ROOT / "logs" / "contributions.json"

# PLAN-06 proof categories, in render order.
CATEGORIES = ("merged", "open", "no-PR", "closed", "protocol-due", "post-close")
_SCOUT_DIR_CAP = 2500  # bound the workspace walk so a pathological tree can't hang the beat
_DEP_LINE_RX = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def _category(status: str) -> str:
    s = status.lower().strip().replace("_", "-")
    if s == "merged":
        return "merged"
    if s in {"closed", "rejected"}:
        return "closed"
    if s in {"post-close", "postclose"}:
        return "post-close"
    if s in {"protocol-due", "needs-bump", "stale", "needs-response"}:
        return "protocol-due"
    if s in {"no-pr", "nopr", "workspace", "scouted", "none", "planned"}:
        return "no-PR"
    return "open"  # open / draft / waiting-on-maintainer / unknown


def _public(value: Any) -> str:
    """Redaction gate: only short public strings reach the surface; local paths never do."""
    text = str(value or "").strip()
    if not text or "/Users/" in text or text.startswith(("~", "/")):
        return ""
    return text.replace("|", "\\|")


def _ledger_items(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, dict):
        return []
    items = obj.get("contributions") or obj.get("items") or obj.get("prs") or []
    if isinstance(items, dict):
        items = list(items.values())
    return [i for i in items if isinstance(i, dict)]


def _normalize(item: dict[str, Any], stale_before: str = "") -> tuple[str, str, str, str]:
    """One hub-ledger item -> (repo, title, url, proof category). Speaks both the refresh-ledger
    contract (upstream_repo/pr_state/pr_title/upstream_pr) and the generic repo/status/title one;
    `workspace` and `notes` never pass this gate. An open PR whose last update predates
    `stale_before` (derived from the SOURCE stamp, not the clock) is derived protocol-due —
    the LIFECYCLE.md staleness rule, executable."""
    repo = _public(item.get("upstream_repo") or item.get("repo") or item.get("name") or item.get("id") or "")
    title = _public(item.get("pr_title") or item.get("title"))
    pr = item.get("upstream_pr")
    url = _public(item.get("url") or (f"https://github.com/{repo}/pull/{pr}" if repo and pr else ""))
    status = str(item.get("pr_state") or item.get("status") or item.get("state") or "").strip()
    if item.get("pr_merged_at"):
        status = "merged"
    elif not status and not pr:
        status = "no-PR"
    cat = _category(status or "open")
    updated = str(item.get("pr_updated") or "")[:10]
    if cat == "open" and stale_before and updated and updated < stale_before:
        cat = "protocol-due"
    return repo, title, url, cat


def _stale_before(as_of: str) -> str:
    """The staleness cutoff date, derived from the source stamp so renders stay deterministic."""
    try:
        return (dt.date.fromisoformat(as_of) - dt.timedelta(days=STALE_DAYS)).isoformat()
    except ValueError:
        return ""


def load_sources() -> tuple[list[dict[str, Any]], str, str]:
    """Return (items, source-name, as-of stamp). Local hub checkout wins; else committed cache; else absent."""
    if HUB_LEDGER.exists():
        try:
            obj = yaml.safe_load(HUB_LEDGER.read_text()) or {}
            stamp = dt.datetime.fromtimestamp(HUB_LEDGER.stat().st_mtime, dt.UTC).strftime("%Y-%m-%d")
            return _ledger_items(obj), "local hub checkout", stamp
        except Exception:
            pass
    if CACHE.exists():
        try:
            obj = json.loads(CACHE.read_text())
            return _ledger_items(obj), "committed cache", str(obj.get("fetched") or "unknown")
        except Exception:
            pass
    return [], "absent", ""


def refresh_cache() -> bool:
    """Pull the hub LEDGER.yaml via the read-only GitHub contents API into the committed cache."""
    try:
        raw = subprocess.run(
            ["gh", "api", f"repos/{HUB_REPO}/contents/LEDGER.yaml", "--jq", ".content"],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
            check=True,
        ).stdout
        obj = yaml.safe_load(base64.b64decode(raw)) or {}
        items = _ledger_items(obj)
        if not items:
            print(f"refresh: {HUB_REPO} LEDGER.yaml has no contribution items; cache left untouched")
            return False
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
            "source": f"{HUB_REPO}/LEDGER.yaml",
            "contributions": items,
        }
        CACHE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"refresh: cached {len(items)} item(s) from {HUB_REPO}")
        return True
    except Exception as exc:  # fail-open: the beat never hangs on GitHub
        print(f"refresh: unavailable ({type(exc).__name__}); mirror will render from existing sources")
        return False


def backflow_tally() -> dict[str, int]:
    """Optional inward-lens tally: signals routed per receiving organ. Absent manifest -> {}."""
    if not BACKFLOW.exists():
        return {}
    try:
        obj = yaml.safe_load(BACKFLOW.read_text()) or {}
    except Exception:
        return {}
    organs = obj.get("organs")
    if isinstance(organs, dict):  # the manifest's real contract: organs -> [signal, ...]
        return {_public(name) or "unrouted": len(sigs) for name, sigs in organs.items() if isinstance(sigs, list)}
    signals = obj.get("signals") or obj.get("entries") or obj.get("backflow") or []
    if isinstance(signals, dict):
        signals = list(signals.values())
    tally: dict[str, int] = {}
    for sig in signals:
        if isinstance(sig, dict):
            organ = _public(sig.get("organ") or sig.get("target") or "unrouted") or "unrouted"
            tally[organ] = tally.get(organ, 0) + 1
    return tally


def verify_estate() -> tuple[int, int, int, list[str], list[str]]:
    """Verify the certified register: (total, present, cited, absent-ids, optional-absent-ids).
    A non-optional local artifact gone absent is DRIFT — surfaced, never silently rotted."""
    try:
        entries = (yaml.safe_load(ESTATE.read_text()) or {}).get("artifacts") or []
    except Exception:
        return 0, 0, 0, ["estate-register-unreadable"], []
    present = cited = 0
    absent: list[str] = []
    optional_absent: list[str] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if str(e.get("presence", "local")) != "local":
            cited += 1
            continue
        loc = str(e.get("location", ""))
        path = Path(os.path.expanduser(loc)) if loc.startswith(("~", "/")) else ROOT / loc
        if path.exists():
            present += 1
        elif e.get("optional"):
            optional_absent.append(str(e.get("id", loc)))
        else:
            absent.append(str(e.get("id", loc)))
    return len([e for e in entries if isinstance(e, dict)]), present, cited, sorted(absent), sorted(optional_absent)


def _engaged_names(items: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in items:
        for field in ("upstream_repo", "repo", "name"):
            tail = str(item.get(field) or "").split("/")[-1].lower().replace("_", "-")
            tail = tail.removeprefix("contrib--")
            if tail:
                names.add(tail)
    return names


def _deps_from_manifest(path: Path) -> set[str]:
    deps: set[str] = set()
    try:
        if path.name == "package.json":
            obj = json.loads(path.read_text())
            for key in ("dependencies", "devDependencies"):
                deps |= {d.split("/")[-1].lower() for d in (obj.get(key) or {})}
        elif path.name == "pyproject.toml":
            import tomllib

            obj = tomllib.loads(path.read_text())
            reqs = list(obj.get("project", {}).get("dependencies") or [])
            for extra in (obj.get("project", {}).get("optional-dependencies") or {}).values():
                reqs += list(extra)
            for req in reqs:
                m = _DEP_LINE_RX.match(str(req).strip())
                if m:
                    deps.add(m.group(1).lower())
        else:  # requirements*.txt
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "-", ".", "/")):
                    continue
                m = _DEP_LINE_RX.match(line)
                if m:
                    deps.add(m.group(1).lower())
    except Exception:
        pass
    return {d.replace("_", "-") for d in deps if d}


def scout(items: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """The autopoietic limb: look INWARD (our own dependency manifests, bounded walk) and derive
    the OUTWARD pool — upstreams we already lean on hardest that we have never engaged. Returns
    [(dependency, distinct-repos-using-it)], heaviest first, engaged upstreams excluded."""
    if not SCOUT_ON:
        return []
    engaged = _engaged_names(items)
    own = {"limen", "ianva", "moneta", "organvm-engine", "limen-mcp"}
    usage: dict[str, set[str]] = {}
    scanned = 0
    workspace = HOME / "Workspace"
    if not workspace.is_dir():
        return []
    roots: list[Path] = []
    for org in sorted(workspace.iterdir()):
        if org.name.startswith((".", "_")) or not org.is_dir():
            continue
        roots.append(org)
        for sub in sorted(org.iterdir()):
            scanned += 1
            if scanned > _SCOUT_DIR_CAP:
                break
            if sub.is_dir() and not sub.name.startswith((".", "_")) and sub.name != "node_modules":
                roots.append(sub)
        if scanned > _SCOUT_DIR_CAP:
            break
    for repo_root in roots:
        deps: set[str] = set()
        for manifest in ("requirements.txt", "pyproject.toml", "package.json"):
            p = repo_root / manifest
            if p.is_file():
                deps |= _deps_from_manifest(p)
        for dep in deps:
            if dep in own or any(dep in e or e in dep for e in engaged):
                continue
            usage.setdefault(dep, set()).add(repo_root.name)
    pool = [(dep, len(repos)) for dep, repos in usage.items() if len(repos) >= 2]
    pool.sort(key=lambda t: (-t[1], t[0]))
    return pool[:SCOUT_CAP]


def lifecycle_debt(items: list[dict[str, Any]], stale_before: str) -> list[tuple[str, str]]:
    """The terminal-hygiene audit (LIFECYCLE.md): merged/closed contributions whose workspace has
    no recorded closeout are reap-owed — (tracking repo or upstream, category) queued receipts."""
    debt: list[tuple[str, str]] = []
    for item in items:
        repo, _, _, cat = _normalize(item, stale_before)
        if cat in {"merged", "closed", "post-close"} and not (item.get("reaped") or item.get("closed_out")):
            where = _public(item.get("tracking_remote")) or repo or "unknown"
            debt.append((where, cat))
    debt.sort()
    return debt


def render(
    items: list[dict[str, Any]],
    source: str,
    as_of: str,
    flow: dict[str, int],
    pool: list[tuple[str, int]],
    estate: tuple[int, int, int, list[str], list[str]],
) -> str:
    stale_before = _stale_before(as_of)
    counts = dict.fromkeys(CATEGORIES, 0)
    rows: list[tuple[str, str, str, str]] = []
    for item in items:
        row = _normalize(item, stale_before)
        counts[row[3]] += 1
        rows.append(row)
    rows.sort(key=lambda r: (CATEGORIES.index(r[3]), r[0]))
    debt = lifecycle_debt(items, stale_before)
    total, present, cited, absent, optional_absent = estate

    lines = [
        "# SPECVLVM — the contributions mirror",
        "",
        "> Outward to learn inward: each upstream is a lens on wiring worth absorbing; community and",
        "> name recognition accrue as byproducts of genuine value. Rendered by",
        "> `scripts/contributions-organ.py` from hub-ledger outputs only (PLAN-06 owner packet 04 —",
        "> limen is the owner surface). **Nothing here sends** — every outbound act is the human's hand.",
        "",
    ]
    if source == "absent":
        lines += [
            "## Staleness receipt",
            "",
            "The hub ledger is unreachable: the local hub checkout is absent and no cache has been",
            f"fetched yet. Restore the `{HUB_REPO}` checkout or run with `--refresh` (PLAN-06 owner",
            "packet 01 tracks the hub-side repair). An honest mirror shows its dust — counts below",
            "are empty, not zero-by-achievement.",
            "",
        ]
    else:
        lines += [f"_Source: {source} (as of {as_of}) · {len(rows)} tracked contribution(s)_", ""]
    lines += ["## Proof", "", "| " + " | ".join(CATEGORIES) + " |", "|" + "---|" * len(CATEGORIES)]
    lines += ["| " + " | ".join(str(counts[c]) for c in CATEGORIES) + " |", ""]
    if rows:
        lines += ["| upstream | contribution | ref | proof |", "|---|---|---|---|"]
        lines += [f"| {r or '—'} | {t or '—'} | {u or '—'} | {c} |" for r, t, u, c in rows]
        lines += [""]
    lines += [
        "## Lifecycle (the audit of `LIFECYCLE.md`)",
        "",
        f"Staleness rule: an open PR untouched since before {stale_before or 'n/a'} "
        f"({STALE_DAYS}d before the source stamp) renders protocol-due — a bump is owed, staged,",
        "and fired one-at-a-time by the human hand (never batch-bumped).",
        "",
    ]
    if debt:
        lines += [
            f"**Lifecycle debt — {len(debt)} workspace(s) reap-owed** (terminal PR, no recorded closeout:",
            "archive the tracking repo, settle the fork, mark the ledger entry closed-out):",
            "",
        ]
        lines += [f"- `{where}` — {cat}" for where, cat in debt]
    else:
        lines += ["No lifecycle debt: every terminal contribution has a recorded closeout."]
    lines += ["", "## The autopoietic pool — inward-derived outward opportunities", ""]
    if pool:
        lines += [
            "The scout limb walked our own dependency manifests: these are the upstreams we lean on",
            "hardest and have never engaged — the next places to study wiring. Pooled for",
            "scout/fieldwork vetting; adoption and every send stay human-gated.",
            "",
            "| dependency | used across our repos |",
            "|---|---|",
        ]
        lines += [f"| {dep} | {n} |" for dep, n in pool]
    elif SCOUT_ON:
        lines += ["The scout walk found no unengaged dependency used across 2+ of our repos."]
    else:
        lines += ["Scout limb gated off (`LIMEN_CONTRIB_SCOUT=0`)."]
    lines += ["", "## Backflow (the inward product)", ""]
    if flow:
        lines += [f"- **{organ}** — {n} signal(s) routed inward" for organ, n in sorted(flow.items())]
    else:
        lines += ["- backflow manifest not readable from this host — the tally renders where it is."]
    lines += [
        "",
        "## Estate register (`ESTATE.yaml`)",
        "",
        f"{total} artifacts registered — {present} verified present locally, {cited} cited "
        f"(remote/receipt), {len(absent)} DRIFT, {len(optional_absent)} optional-absent.",
    ]
    if absent:
        lines += ["", "**DRIFT — registered artifacts gone absent (repair or re-home, never delete the entry):**", ""]
        lines += [f"- `{a}`" for a in absent]
    if optional_absent:
        lines += ["", f"_Optional-absent (expected): {', '.join(f'`{a}`' for a in optional_absent)}_"]
    lines += [
        "",
        "## The estate this mirror reflects",
        "",
        f"- Hub: `{HUB_REPO}` (generated LEDGER; state surface)",
        "- Engines: `organvm_engine.contrib` (A) + `contrib_engine/` in orchestration-start-here (B)",
        "- Workspaces: the `contrib--*` tracking repos, one per upstream",
        "- Rules: `organs/contributions/LIFECYCLE.md` · Register: `organs/contributions/ESTATE.yaml`",
        "- Charter: `organs/contributions/CHARTER.md` · Kernel: `organs/contributions/KERNEL.md`",
        "",
    ]
    return "\n".join(lines)


BUMP_RECEIPTS = ORGAN_HOME / "bump-receipts.jsonl"
BUMP_COOLDOWN_DAYS = int(os.environ.get("LIMEN_CONTRIB_BUMP_COOLDOWN", "14"))
# A genuine, low-pressure nudge — value first, never a nag (the doctrine: standing accrues from
# genuine value, community recognition is a byproduct). {repo} is filled from the ledger item.
BUMP_TEXT = (
    "Hi — a friendly check-in on this PR. No pressure at all: I'm happy to rebase onto the latest "
    "default branch or address any feedback whenever you have a chance. Thanks for maintaining "
    "{repo} and for taking a look."
)


def _recent_bumps() -> dict[str, str]:
    """Map PR url -> last-fired ISO date from the receipts log, so a PR is never re-bumped inside the
    cooldown. Malformed/absent lines are skipped (fail-open — a missing log just means no cooldown)."""
    out: dict[str, str] = {}
    if not BUMP_RECEIPTS.exists():
        return out
    for line in BUMP_RECEIPTS.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("fired") and rec.get("url"):
            out[rec["url"]] = str(rec.get("ts", ""))[:10]
    return out


def bump_one(items: list[dict[str, Any]], as_of: str, *, armed: bool) -> int:
    """The single outward EFFECTOR (dark by default). Fires exactly ONE reversible `gh pr comment`
    on the OLDEST protocol-due PR — never a batch (the 2026-04-21 batch-bump is a codified LIFECYCLE
    violation; one-at-a-time is the rule). Without an arm (LIMEN_CONTRIB_BUMP=1 or --arm) it only
    PREVIEWS and sends nothing, preserving the organ's 'never sends' invariant as the default. Armed,
    it posts one comment and appends a reversible receipt, honoring a per-PR cooldown so no upstream
    is ever re-nagged. A PR comment is deletable — reversible — but it is still an OUTWARD send, so
    arming is a deliberate human decision, not the beat's default."""
    stale_before = _stale_before(as_of)
    recent = _recent_bumps()
    cutoff = ""
    try:
        cutoff = (dt.date.fromisoformat(as_of[:10]) - dt.timedelta(days=BUMP_COOLDOWN_DAYS)).isoformat()
    except ValueError:
        pass
    due: list[tuple[str, str, str, str]] = []
    for item in items:
        repo, title, url, cat = _normalize(item, stale_before)
        if cat != "protocol-due" or not url:
            continue
        last = recent.get(url, "")
        if last and cutoff and last >= cutoff:
            continue  # already nudged inside the cooldown window — never re-nag
        updated = str(item.get("pr_updated") or "")[:10]
        due.append((updated, repo, title, url))
    if not due:
        print("bump: no protocol-due PR eligible (all fresh or within cooldown)")
        return 0
    due.sort()  # oldest-updated first — the most-owed nudge
    _updated, repo, title, url = due[0]
    body = BUMP_TEXT.format(repo=repo or "this project")
    if not armed:
        print(
            f"bump [DARK] would post 1 of {len(due)} eligible bump(s): {url}\n"
            f"  PR: {title or '(untitled)'}\n"
            f"  arm with LIMEN_CONTRIB_BUMP=1 (or --arm) to fire this one reversible comment"
        )
        return 0
    cp = subprocess.run(["gh", "pr", "comment", url, "--body", body], capture_output=True, text=True)
    fired = cp.returncode == 0
    ts = dt.datetime.now(dt.UTC).isoformat()
    ORGAN_HOME.mkdir(parents=True, exist_ok=True)
    with BUMP_RECEIPTS.open("a") as fh:
        fh.write(json.dumps({"ts": ts, "repo": repo, "url": url, "title": title, "fired": fired}) + "\n")
    if fired:
        print(f"bump: posted 1 reversible comment on {url} (receipt journaled)")
        return 0
    print(f"bump: FAILED on {url}: {cp.stderr.strip()[:200]}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="SPECVLVM — render the contributions mirror")
    ap.add_argument("--refresh", action="store_true", help="refresh the ledger cache from GitHub first (read-only)")
    ap.add_argument("--check", action="store_true", help="exit 0 iff the committed mirror matches a fresh render")
    ap.add_argument(
        "--bump",
        action="store_true",
        help="EFFECTOR: fire one reversible bump on the oldest protocol-due PR (DARK unless armed)",
    )
    ap.add_argument("--arm", action="store_true", help="with --bump, actually post (else preview only)")
    args = ap.parse_args()

    if args.refresh or os.environ.get("LIMEN_CONTRIB_REFRESH") == "1":
        refresh_cache()

    items, source, as_of = load_sources()
    stale_before = _stale_before(as_of)
    pool = scout(items)
    estate = verify_estate()
    body = render(items, source, as_of, backflow_tally(), pool, estate)

    if args.bump:
        armed = args.arm or os.environ.get("LIMEN_CONTRIB_BUMP") == "1"
        return bump_one(items, as_of, armed=armed)

    if args.check:
        current = MIRROR.read_text() if MIRROR.exists() else ""
        if current == body:
            print(f"mirror current ({source}; {len(items)} item(s))")
            return 0
        print("mirror STALE: re-run scripts/contributions-organ.py to re-render")
        return 1

    ORGAN_HOME.mkdir(parents=True, exist_ok=True)
    changed = not MIRROR.exists() or MIRROR.read_text() != body
    if changed:
        MIRROR.write_text(body)
    pool_payload = (
        json.dumps(
            {
                "derived_from": "workspace dependency manifests (the inward gaze)",
                "as_of_source": as_of,
                "pool": [{"dependency": d, "used_in_repos": n} for d, n in pool],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if not OPPORTUNITIES.exists() or OPPORTUNITIES.read_text() != pool_payload:
        OPPORTUNITIES.write_text(pool_payload)
    counts: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    for item in items:
        counts[_normalize(item, stale_before)[3]] += 1
    total, present, cited, absent, optional_absent = estate
    SIGNAL.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL.write_text(
        json.dumps(
            {
                "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "organ": "contributions",
                "source": source,
                "as_of": as_of,
                "stale": source == "absent",
                "total": len(items),
                "counts": counts,
                "lifecycle_debt": len(lifecycle_debt(items, stale_before)),
                "opportunities": len(pool),
                "estate": {
                    "registered": total,
                    "present": present,
                    "cited": cited,
                    "drift": absent,
                    "optional_absent": optional_absent,
                },
                "mirror": "organs/contributions/MIRROR.md",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(
        f"mirror {'re-rendered' if changed else 'unchanged'} ({source}; {len(items)} item(s); "
        f"pool {len(pool)}; estate {present}+{cited}/{total}, drift {len(absent)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
