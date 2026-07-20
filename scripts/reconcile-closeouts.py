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
    blob = " ".join(str(claim.get(k, "")) for k in ("text", "subject")) + " " + " ".join(
        str(r) for r in claim.get("receipts", []) or []
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
        return {"id": claim.get("id"), "verdict": "HOMED_ELSEWHERE", "refs": refs,
                "detail": f"in-repo artifact {artifact!r} absent; durable home is external: {external}"}

    if not refs:
        return {"id": claim.get("id"), "verdict": "UNRECEIPTED", "refs": [],
                "detail": "done claim cites no PR / receipt — cannot confirm"}

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

    if missing:
        return {"id": claim.get("id"), "verdict": "PR_MISSING", "refs": refs,
                "detail": f"cited PR(s) do not exist: {', '.join(missing)}"}
    if unmerged:
        return {"id": claim.get("id"), "verdict": "DONE_UNVERIFIED", "refs": refs,
                "detail": f"claims done but PR(s) not merged: {', '.join(unmerged)}"}
    if miscited and not merged:
        return {"id": claim.get("id"), "verdict": "MISCITED", "refs": refs,
                "detail": f"cited MERGED PR unrelated to subject: {', '.join(miscited)}"}
    return {"id": claim.get("id"), "verdict": "VERIFIED", "refs": refs,
            "detail": f"backed by merged PR(s): {', '.join(merged)}"}


HARD = {"DONE_UNVERIFIED", "PR_MISSING"}  # verdicts that fail --check (concrete false-closeouts)


def _board_claims(since_hours: int, limit: int | None) -> list[dict]:
    """Closeout claims from the live board: each done task's done dispatch_log entries, within the
    window and citing a PR (only PR-citing claims are cheap to reconcile against GitHub)."""
    data = yaml.safe_load((ROOT / "tasks.yaml").read_text()) or {}
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
            claims.append({"id": t.get("id"), "subject": t.get("title", ""), "text": text,
                           "repo": t.get("repo", "")})
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
            "id": rec.get("id"), "subject": rec.get("subject", ""), "text": rec.get("text", ""),
            "repo": rec.get("repo", ""), "receipts": receipts,
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
    return {"counts": counts, "findings": findings,
            "failing": [f for f in findings if f["verdict"] in HARD]}


def _emit(report: dict) -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "closeout-reconcile.json").write_text(json.dumps(report, indent=2))


def _doctor() -> int:
    """Network-free proof that every classification branch is correct."""
    fake = {
        ("o", "r", "1"): (True, "OPEN"),      # claimed done, still open  → DONE_UNVERIFIED
        ("o", "r", "2"): (True, "MERGED"),    # merged, subject-consistent → VERIFIED
        ("o", "r", "3"): (False, None),       # missing                    → PR_MISSING
        ("o", "r", "4"): (True, "MERGED"),    # merged but unrelated title → MISCITED
    }
    titles = {("o", "r", "2"): "harden the widget parser", ("o", "r", "4"): "arca vault ciphertext chunk"}
    cases = [
        ({"id": "c1", "subject": "harden widget parser", "repo": "o/r", "text": "done #1"}, "DONE_UNVERIFIED"),
        ({"id": "c2", "subject": "harden widget parser", "repo": "o/r", "text": "done #2"}, "VERIFIED"),
        ({"id": "c3", "subject": "x", "repo": "o/r", "text": "done #3"}, "PR_MISSING"),
        ({"id": "c4", "subject": "court hearing record", "repo": "o/r", "text": "done #4"}, "MISCITED"),
        ({"id": "c5", "subject": "record court grant", "repo": "o/r", "text": "homed in matter.json",
          "repo_artifact": "no/such/matter.json", "external_home": "private calendar"}, "HOMED_ELSEWHERE"),
        ({"id": "c6", "subject": "misc", "repo": "o/r", "text": "all good, fixed point"}, "UNRECEIPTED"),
    ]
    ok = True
    for claim, expected in cases:
        got = classify_claim(claim, lambda o, r, n: fake.get((o, r, n), (False, None)),
                             lambda o, r, n: titles.get((o, r, n), ""))["verdict"]
        flag = "ok" if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"  [{flag}] {claim['id']}: expected {expected}, got {got}")
    print("doctor: PASS" if ok else "doctor: FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="verify claimed-done closeouts against ground truth")
    ap.add_argument("--doctor", action="store_true", help="network-free classifier self-test")
    ap.add_argument("--check", action="store_true", help="probe the live board; exit 1 on false-closeouts")
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
    elif args.check:
        # both claim sources: durable board dispatch_log done-claims AND captured ephemeral session
        # closeouts (logs/session-claims.jsonl). Combined then capped so the GitHub probe stays bounded.
        claims = _board_claims(args.since_hours, None) + _session_claims(args.since_hours, None)
        if args.limit:
            claims = claims[: args.limit]
    else:
        ap.error("one of --doctor / --check / --fixture is required")

    report = _run(claims)
    if args.json or args.check:
        _emit(report)

    if not args.quiet:
        print(f"=== CLOSEOUT RECONCILIATION ({len(claims)} claim(s)) ===")
        for v, n in sorted(report["counts"].items()):
            flag = "⚠ " if v in HARD else "  "
            print(f"{flag}{v:16} {n}")
        for f in report["failing"]:
            print(f"    {f['verdict']}: {f['id']}  — {f['detail']}")

    return 1 if report["failing"] else 0


if __name__ == "__main__":
    sys.exit(main())
