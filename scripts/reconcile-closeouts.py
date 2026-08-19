#!/usr/bin/env python3
"""reconcile-closeouts.py — verify CLAIMED-done work against ground truth.

`verify-dispatch.py` babysits `status=dispatched` (in-flight) claims. This babysits the
COMPLEMENT: `status=done` CLOSEOUT claims — the "solved / shipped / merged" assertions that,
once written, are trusted forever. A completed session (or a done task's dispatch_log) claims an
outcome; this probes whether that outcome is real. Verdicts:

  VERIFIED        : claim cites a MERGED PR (subject-consistent) — real
  DONE_UNVERIFIED : claims done but its cited PR is OPEN/CLOSED (unmerged) — the
                    "PR #1203 solved at root" false-closeout (the PR is CONFLICTING/DIRTY)
  PR_MISSING      : cites a PR that does not exist (deleted / wrong number)
  MISCITED        : cites a MERGED PR whose subject is unrelated to the claim — the
                    #1068→arca, #361→docs phantom citations (advisory)
  HOMED_ELSEWHERE : the claimed in-repo artifact is absent but a durable EXTERNAL home is
                    named (the Mon-7/20 court record correctly living in the private calendar) —
                    NOT a defect (info)
  UNRECEIPTED     : done but cites no PR/receipt at all — cannot confirm (advisory)

Reuses `verify-dispatch.gh_pr_state` + `PR_RE` (one source for the GitHub state probe).
READ-ONLY: never writes tasks.yaml; emits logs/closeout-reconcile.json.

Usage:
  reconcile-closeouts.py --doctor                        network-free classifier self-test → 0/1
  reconcile-closeouts.py --check [--since-hours N] [--limit N]
                                                         probe both claim sources — board dispatch_log
                                                         done-claims AND captured session closeouts
                                                         (logs/session-claims.jsonl); exit 1 on any
                                                         DONE_UNVERIFIED / PR_MISSING
  reconcile-closeouts.py --fixture PATH [--json]         reconcile a JSON list of claims (live gh)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts/ for _board_custody
from _board_custody import board_path  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))

# --- reuse the GitHub state probe from verify-dispatch (single source) ---------------------------
# verify-dispatch.py has a hyphen (not import-able by name); load it by path and lift gh_pr_state +
# PR_RE so the "does this PR exist / is it merged" logic lives in exactly one place.
_VD = ROOT / "scripts" / "verify-dispatch.py"
try:
    _spec = importlib.util.spec_from_file_location("verify_dispatch", _VD)
    _vd = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_vd)  # type: ignore[union-attr]
    gh_pr_state = _vd.gh_pr_state
    PR_RE = _vd.PR_RE
except Exception:  # pragma: no cover - fallback keeps the predicate runnable in a bare checkout
    PR_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")

    def gh_pr_state(owner, repo, num):  # type: ignore[misc]
        try:
            out = subprocess.run(
                ["gh", "pr", "view", num, "--repo", f"{owner}/{repo}", "--json", "state,mergedAt"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if out.returncode != 0:
                return False, None
            d = json.loads(out.stdout)
            return (True, "MERGED") if d.get("mergedAt") else (True, d.get("state", "OPEN"))
        except Exception:
            return False, None


# --- reuse the finding router from insight-route (single homing engine) ---------------------------
# insight-route.py already homes a finding by owner: org/repo -> a TABVLARIVS board task (via the
# single-writer keeper inbox, deduped vs board + pending tickets), <organ> -> residual, anthony ->
# lever. The effector below is a thin MAPPER onto that engine — it never re-implements routing, and
# never writes a derived file (PREC-2026-07-10). The mutation rides insight-route's OWN existing
# `LIMEN_INSIGHT_ROUTE_APPLY` arm, so no new silent-off valve is introduced (PREC-2026-07-08).
_IR = ROOT / "scripts" / "insight-route.py"
try:
    _spec_ir = importlib.util.spec_from_file_location("insight_route", _IR)
    _ir = importlib.util.module_from_spec(_spec_ir)
    _spec_ir.loader.exec_module(_ir)  # type: ignore[union-attr]
    route_repo_insight = _ir.route_repo_insight
except Exception:  # pragma: no cover - routing is optional; --check/--doctor still run bare
    route_repo_insight = None  # type: ignore[assignment]


HASH_RE = re.compile(r"#(\d+)\b")
# generic tokens that carry no subject signal, so they never count toward claim↔PR-title overlap
_STOP = frozenset(
    "the a an and or of to for in on at is are be by with fix feat chore docs refactor heal "
    "pr prs land landed merge merged ship shipped done complete completed solved resolve closeout "
    "task issue update add remove wip".split()
)


def _tokens(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if w and w not in _STOP and len(w) > 2}


def _parse_ts(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # board `updated` may be offset-less
    except Exception:
        return None


def _gh_pr_title(owner: str, repo: str, num: str) -> str:
    """PR title (for the MISCITED subject check). Kept separate from the reused state probe."""
    try:
        out = subprocess.run(
            ["gh", "pr", "view", num, "--repo", f"{owner}/{repo}", "--json", "title"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode == 0:
            return json.loads(out.stdout).get("title", "") or ""
    except Exception:
        pass
    return ""


def _refs(claim: dict) -> list[tuple[str, str, str]]:
    """Every (owner, repo, num) PR reference in the claim: full github URLs, plus #NNN paired with
    the claim's own repo (owner/repo)."""
    blob = (
        " ".join(str(claim.get(k, "")) for k in ("text", "subject"))
        + " "
        + " ".join(str(r) for r in claim.get("receipts", []) or [])
    )
    refs: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for owner, repo, num in PR_RE.findall(blob):
        key = (owner, repo, num)
        if key not in seen:
            seen.add(key)
            refs.append(key)
    repo_slug = str(claim.get("repo") or "")
    if "/" in repo_slug:
        owner, repo = repo_slug.split("/", 1)
        for num in HASH_RE.findall(blob):
            key = (owner, repo, num)
            if key not in seen:
                seen.add(key)
                refs.append(key)
    return refs


def classify_claim(claim: dict, state_fn=gh_pr_state, title_fn=_gh_pr_title) -> dict:
    """Pure classifier: a claim dict + a (owner,repo,num)->(exists,state) probe → a verdict.

    claim = {id, subject, text, repo, receipts:[...], external_home?, repo_artifact?}
    The probe is injectable so --doctor tests every branch with no network.
    """
    refs = _refs(claim)

    # HOMED_ELSEWHERE: an in-repo artifact was claimed but is absent, and a durable external home is
    # named (the 7/20 calendar case). This is explicit claim metadata, never guessed from prose.
    artifact = claim.get("repo_artifact")
    external = claim.get("external_home")
    if artifact and external and not (ROOT / str(artifact)).exists():
        return {
            "id": claim.get("id"),
            "verdict": "HOMED_ELSEWHERE",
            "refs": refs,
            "detail": f"in-repo artifact {artifact!r} absent; durable home is external: {external}",
        }

    if not refs:
        return {
            "id": claim.get("id"),
            "verdict": "UNRECEIPTED",
            "refs": [],
            "detail": "done claim cites no PR / receipt — cannot confirm",
        }

    merged, unmerged, missing, miscited = [], [], [], []
    subj_tokens = _tokens(f"{claim.get('subject', '')} {claim.get('text', '')}")
    for owner, repo, num in refs:
        exists, state = state_fn(owner, repo, num)
        slug = f"{owner}/{repo}#{num}"
        if not exists:
            missing.append(slug)
        elif state == "MERGED":
            title = title_fn(owner, repo, num) if title_fn else ""
            if subj_tokens and title and not (subj_tokens & _tokens(title)):
                miscited.append(f"{slug} ({title})")
            else:
                merged.append(slug)
        else:  # OPEN / CLOSED — claimed done but not merged
            unmerged.append(f"{slug}:{state}")

    # A done-claim is backed iff there EXISTS a subject-matching merged receipt — not iff EVERY
    # cited ref is clean. Co-cited refs that are missing, unmerged, or subject-unrelated are noise
    # (heal *targets* — the id-suffix issue a cifix healed; stale/typo'd numbers; superseded PRs),
    # never disproof of a real merged receipt. (2026-07-18 field finding: HEAL-624 cites both merged
    # fix #1116 AND its still-open target #624; the claim is done because #1116 merged, not undone
    # because #624 is open. The prior any-ref-fails precedence turned 4 such multi-ref claims into
    # phantom DONE_UNVERIFIED / PR_MISSING findings.)
    if merged:
        detail = f"backed by merged PR(s): {', '.join(merged)}"
        noise = missing + unmerged + miscited
        if noise:
            detail += f"; ignored co-ref(s): {', '.join(noise)}"
        return {"id": claim.get("id"), "verdict": "VERIFIED", "refs": refs, "detail": detail}

    # No subject-matching merged receipt — escalate to the true problem. Unmerged is the most
    # actionable signal (a real open PR to land) → then a wrong/missing number → then a merged-but-
    # off-subject citation with nothing backing the claim.
    if unmerged:
        return {
            "id": claim.get("id"),
            "verdict": "DONE_UNVERIFIED",
            "refs": refs,
            "detail": f"claims done but PR(s) not merged: {', '.join(unmerged)}",
        }
    if missing:
        return {
            "id": claim.get("id"),
            "verdict": "PR_MISSING",
            "refs": refs,
            "detail": f"cited PR(s) do not exist: {', '.join(missing)}",
        }
    return {
        "id": claim.get("id"),
        "verdict": "MISCITED",
        "refs": refs,
        "detail": f"cited MERGED PR unrelated to subject: {', '.join(miscited)}",
    }


HARD = {"DONE_UNVERIFIED", "PR_MISSING"}  # verdicts that fail --check (concrete false-closeouts)


# --- effector: home HARD findings to their durable owner (the BRANCH rung) ------------------------
# A sensor whose real findings aren't routed to a durable owner is a defect. A HARD finding — a task
# claims done but its receipt is unverified — is stranded work on the claim's OWN repo, so it homes as
# a board task on that repo. VERIFIED / MISCITED / HOMED_ELSEWHERE / UNRECEIPTED are not stranded work
# and never route. Safe to auto-home ONLY because the classifier is precise (the merged-receipt-EXISTS
# fix): before it, the 4 phantom findings would have spawned junk tasks.
def _finding_to_insight(finding: dict, claim_repo: str) -> dict | None:
    """Map a HARD reconcile finding → an insight-route insight dict (the org/repo → board-task lane).
    Returns None when the finding is not stranded work or has no routable repo."""
    if finding.get("verdict") not in HARD:
        return None
    if not claim_repo or "/" not in claim_repo:
        return None  # no org/repo owner to home it on
    cid = finding.get("id") or "unknown"
    return {
        "id": f"CLOSEOUT-{cid}",  # stable per claim → insight-route dedup skips repeats across beats
        "owner": claim_repo,
        "title": f"reconcile: {cid} claims done but receipt unverified",
        "detail": finding.get("detail", ""),
        "suggested_action": "land the cited PR, or correct the done-claim's receipt / status",
        "source": "closeout-reconcile",  # NOT "tasks.yaml" — that string triggers the board-echo skip
        "severity": "high" if finding.get("verdict") == "DONE_UNVERIFIED" else "medium",
    }


def _route_findings(claims: list[dict], findings: list[dict], apply: bool, router=None) -> list[dict]:
    """Home each HARD finding via insight-route's org/repo lane. `apply` is insight-route's OWN arm
    (LIMEN_INSIGHT_ROUTE_APPLY): False → the router prints a dry-run plan and writes nothing. Returns
    the routed plan for the report. `router` is injectable so --doctor exercises the mapper offline."""
    router = router if router is not None else route_repo_insight
    repo_by_id = {c.get("id"): c.get("repo", "") for c in claims}
    routed: list[dict] = []
    if router is None:  # insight-route unavailable (bare checkout) — nothing to route
        return routed
    stats = {"cap_left": int(os.environ.get("LIMEN_INSIGHT_ROUTE_MAX", "5")),
             "created": 0, "echo": 0, "deferred": 0}
    for f in findings:
        insight = _finding_to_insight(f, repo_by_id.get(f.get("id"), ""))
        if insight is None:
            continue
        router(insight, apply, stats)
        routed.append({"insight_id": insight["id"], "owner": insight["owner"], "verdict": f["verdict"]})
    return routed


def _board_claims(since_hours: int, limit: int | None) -> list[dict]:
    """Closeout claims from the live board: each done task's done dispatch_log entries, within the
    window and citing a PR (only PR-citing claims are cheap to reconcile against GitHub)."""
    data = yaml.safe_load(board_path(ROOT / "tasks.yaml").read_text()) or {}
    now = datetime.now(timezone.utc)
    claims: list[dict] = []
    for t in data.get("tasks", []):
        if t.get("status") != "done":
            continue
        upd = _parse_ts(t.get("updated"))
        if since_hours and upd and (now - upd).total_seconds() > since_hours * 3600:
            continue
        for e in t.get("dispatch_log") or []:
            if str(e.get("status")) != "done":
                continue
            text = f"{e.get('session_id', '')} {e.get('output', '')}"
            if not (PR_RE.search(text) or HASH_RE.search(text)):
                continue
            claims.append({"id": t.get("id"), "subject": t.get("title", ""), "text": text, "repo": t.get("repo", "")})
    if limit:
        claims = claims[:limit]
    return claims


def _session_claims(since_hours: int, limit: int | None) -> list[dict]:
    """Closeout claims captured from ephemeral SESSION transcripts (`logs/session-claims.jsonl`,
    written by `capture-session-claim.py` at SessionEnd). This is the complement of `_board_claims`:
    the board tracks durable dispatch_log done-claims; this tracks the "Completed"-pane session
    closeouts that were persisted nowhere reconcilable before. Only a `closed` claim that cites a
    PR/#NNN is cheap to check against GitHub; the latest record per session wins."""
    ledger = ROOT / "logs" / "session-claims.jsonl"
    if not ledger.exists():
        return []
    now = datetime.now(timezone.utc)
    latest: dict[str, dict] = {}
    for ln in ledger.read_text(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if not rec.get("closed"):
            continue
        ts = _parse_ts(rec.get("ts"))
        if since_hours and ts and (now - ts).total_seconds() > since_hours * 3600:
            continue
        receipts = rec.get("receipts") or []
        blob = f"{rec.get('subject', '')} {rec.get('text', '')} " + " ".join(str(r) for r in receipts)
        if not (PR_RE.search(blob) or HASH_RE.search(blob)):
            continue
        latest[rec.get("id")] = {
            "id": rec.get("id"),
            "subject": rec.get("subject", ""),
            "text": rec.get("text", ""),
            "repo": rec.get("repo", ""),
            "receipts": receipts,
        }
    claims = list(latest.values())
    if limit:
        claims = claims[:limit]
    return claims


def _run(claims: list[dict], state_fn=gh_pr_state, title_fn=_gh_pr_title) -> dict:
    findings = [classify_claim(c, state_fn, title_fn) for c in claims]
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    return {"counts": counts, "findings": findings, "failing": [f for f in findings if f["verdict"] in HARD]}


def _emit(report: dict) -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "closeout-reconcile.json").write_text(json.dumps(report, indent=2))


def _doctor() -> int:
    """Network-free proof that every classification branch is correct."""
    fake = {
        ("o", "r", "1"): (True, "OPEN"),  # claimed done, still open  → DONE_UNVERIFIED
        ("o", "r", "2"): (True, "MERGED"),  # merged, subject-consistent → VERIFIED
        ("o", "r", "3"): (False, None),  # missing                    → PR_MISSING
        ("o", "r", "4"): (True, "MERGED"),  # merged but unrelated title → MISCITED
    }
    titles = {("o", "r", "2"): "harden the widget parser", ("o", "r", "4"): "arca vault ciphertext chunk"}
    cases = [
        ({"id": "c1", "subject": "harden widget parser", "repo": "o/r", "text": "done #1"}, "DONE_UNVERIFIED"),
        ({"id": "c2", "subject": "harden widget parser", "repo": "o/r", "text": "done #2"}, "VERIFIED"),
        ({"id": "c3", "subject": "x", "repo": "o/r", "text": "done #3"}, "PR_MISSING"),
        ({"id": "c4", "subject": "court hearing record", "repo": "o/r", "text": "done #4"}, "MISCITED"),
        (
            {
                "id": "c5",
                "subject": "record court grant",
                "repo": "o/r",
                "text": "homed in matter.json",
                "repo_artifact": "no/such/matter.json",
                "external_home": "private calendar",
            },
            "HOMED_ELSEWHERE",
        ),
        ({"id": "c6", "subject": "misc", "repo": "o/r", "text": "all good, fixed point"}, "UNRECEIPTED"),
        # 2026-07-18 field shapes — a subject-matching merged receipt wins over noisy co-refs.
        # (c7) heal-task: merged fix #2 + still-open target #1 → VERIFIED (was phantom DONE_UNVERIFIED).
        (
            {
                "id": "c7",
                "subject": "harden widget parser",
                "repo": "o/r",
                "text": "fix #2 landed, target #1 still open",
            },
            "VERIFIED",
        ),
        # (c8) multi-ref: merged receipt #2 + missing co-ref #3 → VERIFIED (was phantom PR_MISSING).
        ({"id": "c8", "subject": "harden widget parser", "repo": "o/r", "text": "done #2 (see also #3)"}, "VERIFIED"),
        # (c9) genuine over-claim: open #1 + missing #3, NONE merged → still fires DONE_UNVERIFIED.
        ({"id": "c9", "subject": "harden widget parser", "repo": "o/r", "text": "done #1 #3"}, "DONE_UNVERIFIED"),
    ]
    ok = True
    for claim, expected in cases:
        got = classify_claim(
            claim, lambda o, r, n: fake.get((o, r, n), (False, None)), lambda o, r, n: titles.get((o, r, n), "")
        )["verdict"]
        flag = "ok" if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"  [{flag}] {claim['id']}: expected {expected}, got {got}")

    # Effector mapper contract (network-free): a HARD finding maps to a well-formed org/repo insight;
    # a soft verdict maps to None; and _route_findings routes ONLY the HARD ones, to the right owner.
    m_hard = _finding_to_insight({"id": "T-9", "verdict": "DONE_UNVERIFIED", "detail": "d"}, "org/repo")
    m_soft = _finding_to_insight({"id": "T-9", "verdict": "VERIFIED", "detail": "d"}, "org/repo")
    m_norepo = _finding_to_insight({"id": "T-9", "verdict": "PR_MISSING", "detail": "d"}, "")
    map_ok = (
        m_soft is None and m_norepo is None and m_hard is not None
        and m_hard["owner"] == "org/repo" and m_hard["id"] == "CLOSEOUT-T-9"
        and m_hard["source"] == "closeout-reconcile" and m_hard["suggested_action"]
    )
    print(f"  [{'ok' if map_ok else 'FAIL'}] mapper: HARD→insight, soft/no-repo→None")
    seen: list[tuple] = []
    claims_x = [{"id": "T-1", "repo": "org/a"}, {"id": "T-2", "repo": "org/b"}, {"id": "T-3", "repo": "org/c"}]
    findings_x = [{"id": "T-1", "verdict": "DONE_UNVERIFIED", "detail": "d"},
                  {"id": "T-2", "verdict": "VERIFIED", "detail": "d"},
                  {"id": "T-3", "verdict": "PR_MISSING", "detail": "d"}]
    plan = _route_findings(claims_x, findings_x, apply=False,
                           router=lambda ins, ap, st: seen.append((ins["owner"], ins["id"])))
    route_ok = (len(plan) == 2 and {p["verdict"] for p in plan} == {"DONE_UNVERIFIED", "PR_MISSING"}
                and ("org/a", "CLOSEOUT-T-1") in seen and ("org/c", "CLOSEOUT-T-3") in seen)
    print(f"  [{'ok' if route_ok else 'FAIL'}] router: only HARD findings home, to their claim's repo")
    ok = ok and map_ok and route_ok

    print("doctor: PASS" if ok else "doctor: FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="verify claimed-done closeouts against ground truth")
    ap.add_argument("--doctor", action="store_true", help="network-free classifier self-test")
    ap.add_argument("--check", action="store_true", help="probe the live board; exit 1 on false-closeouts")
    ap.add_argument("--apply", action="store_true",
                    help="--check + HOME each HARD finding as a board task via insight-route "
                         "(mutation rides LIMEN_INSIGHT_ROUTE_APPLY; dry-run plan otherwise)")
    ap.add_argument("--fixture", help="reconcile a JSON list of claim dicts (live gh)")
    ap.add_argument("--since-hours", type=int, default=72)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--json", action="store_true", help="write logs/closeout-reconcile.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.doctor:
        return _doctor()

    if args.fixture:
        claims = json.loads(Path(args.fixture).read_text())
    elif args.check or args.apply:
        # both claim sources: durable board dispatch_log done-claims AND captured ephemeral session
        # closeouts (logs/session-claims.jsonl). Combined then capped so the GitHub probe stays bounded.
        claims = _board_claims(args.since_hours, None) + _session_claims(args.since_hours, None)
        if args.limit:
            claims = claims[: args.limit]
    else:
        ap.error("one of --doctor / --check / --apply / --fixture is required")

    report = _run(claims)

    if args.apply:
        # Home HARD findings via insight-route. The mutation rides insight-route's OWN arm; unset →
        # a dry-run plan, so this is safe to beat-wire dark by default (no new silent-off valve).
        route_apply = os.environ.get("LIMEN_INSIGHT_ROUTE_APPLY", "0") == "1"
        report["routed"] = _route_findings(claims, report["findings"], route_apply)

    if args.json or args.check or args.apply:
        _emit(report)

    if not args.quiet:
        print(f"=== CLOSEOUT RECONCILIATION ({len(claims)} claim(s)) ===")
        for v, n in sorted(report["counts"].items()):
            flag = "⚠ " if v in HARD else "  "
            print(f"{flag}{v:16} {n}")
        for f in report["failing"]:
            print(f"    {f['verdict']}: {f['id']}  — {f['detail']}")
        if args.apply:
            routed = report.get("routed", [])
            armed = os.environ.get("LIMEN_INSIGHT_ROUTE_APPLY", "0") == "1"
            print(f"  → routed {len(routed)} HARD finding(s) to board tasks"
                  f"{'' if armed else ' [dry-run — set LIMEN_INSIGHT_ROUTE_APPLY=1 to file]'}")

    return 1 if report["failing"] else 0


if __name__ == "__main__":
    sys.exit(main())
