#!/usr/bin/env python3
"""capture-session-claim.py — the ROOT capture for the closeout-reconciliation organ.

`reconcile-closeouts.py` can only reconcile a claim it can READ. Durable `dispatch_log` done-claims
are already captured on the board, but the *ephemeral* session closeout — the assistant's final
"result: …" line and the receipts it cites — is persisted nowhere richer than {ts,sid,branch}
(`logs/session-closeout.jsonl`, whose shape `quicken.py:_ended_sids()` depends on). That blind spot
is exactly what let a batch of "Completed" sessions over-claim undetected: you cannot reconcile a
claim you never captured.

This is the missing durable claim ledger. As a fail-open SessionEnd hook step it reads THIS
session's transcript, extracts the asserted outcome + cited receipts, and appends one record to a
NEW single-owner ledger `logs/session-claims.jsonl` — in the exact claim shape
`reconcile-closeouts.classify_claim` consumes (`{id, subject, text, repo, receipts}`) — so the organ
reconciles session closeouts too, not just the board's dispatch_log.

  capture-session-claim.py --sid SID [--repo org/repo]   capture one session's closeout claim
  capture-session-claim.py --doctor                      network-free extractor self-test → 0/1

Safe by construction: no-op exit 0 on unknown/missing SID; append-once per SID; never blocks a
session end. The closeout SIGNAL regexes are reused from `agent-session-full-stack-review.py` (one
source), with a local fallback so the capture still runs in a bare checkout.
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

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
LEDGER = ROOT / "logs" / "session-claims.jsonl"

# --- reuse the closeout SIGNAL regexes from full-stack-review (single source) --------------------
# The file has a hyphen (not import-able by name); load it by path and lift the receipt/done/fail
# patterns so "what counts as a cited receipt / a done-signal" lives in exactly one place.
_FSR = ROOT / "scripts" / "agent-session-full-stack-review.py"
try:
    _spec = importlib.util.spec_from_file_location("agent_session_full_stack_review", _FSR)
    _m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_m)  # type: ignore[union-attr]
    RECEIPT_RE = _m.RECEIPT_RE
    DONE_RE = _m.DONE_RE
    FAIL_RE = _m.FAIL_RE
except Exception:  # pragma: no cover - fallback keeps the capture runnable in a bare checkout
    RECEIPT_RE = re.compile(
        r"(https://github\.com/[^)\s]+/pull/\d+|\bPR\s*#?\d+\b|\bcommit\s+[0-9a-f]{7,40}\b|"
        r"\b[0-9a-f]{7,40}\b|\.jsonl\b|\.md\b|\.json\b|artifact|receipt)",
        re.I,
    )
    DONE_RE = re.compile(r"\b(done|complete|completed|verified|passed|merged|pushed|landed|shipped)\b", re.I)
    FAIL_RE = re.compile(
        r"\b(failed|failure|blocked|error|exception|timeout|needs_human|aborted|interrupted)\b", re.I
    )

# The self-narration contract's terminal markers. A closeout line is the strongest claim signal; we
# prefer the message that carries one over the mere last narration line. Horizontal-whitespace only
# ([ \t], never \s) around the marker so the re.M `^` anchor cannot slide onto a preceding blank line
# and swallow the newline — that would leave the captured subject line empty. Group 2 is the headline.
TERMINAL_RE = re.compile(r"^[ \t]*(result|failed|needs input)[ \t]*:(.*)$", re.I | re.M)


def _find_transcript(sid: str) -> Path | None:
    """Locate ~/.claude/projects/*/<sid>.jsonl (mirrors claude-workflow-guard._find_session_jsonl,
    but tolerant: returns None instead of raising so the hook stays a no-op on a missing SID)."""
    if not sid or sid == "unknown":
        return None
    direct = Path(sid).expanduser()
    if direct.exists():
        return direct
    matches = list((Path.home() / ".claude" / "projects").glob(f"*/{sid}.jsonl"))
    return matches[0] if matches else None


def _assistant_texts(records: list[dict]) -> list[str]:
    """Every assistant text block, in order — the final one is the session's last word."""
    texts: list[str] = []
    for rec in records:
        if rec.get("type") != "assistant":
            continue
        for c in rec.get("message", {}).get("content", []) or []:
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                texts.append(c["text"])
    return texts


def extract_claim(records: list[dict], sid: str, repo: str) -> dict | None:
    """Distil a session's transcript into one closeout claim.

    The asserted outcome is the LAST assistant message that carries a terminal marker (result:/
    failed:/needs input:); absent any marker, the final assistant text (the session's last word).
    Receipts are every RECEIPT_RE hit in that outcome. `closed` records whether the session actually
    asserted completion, so an unfinished session is never reconciled as a false-closeout.
    """
    texts = _assistant_texts(records)
    if not texts:
        return None
    outcome = next((t for t in reversed(texts) if TERMINAL_RE.search(t)), texts[-1])
    receipts = sorted({m.group(0).strip() for m in RECEIPT_RE.finditer(outcome)})
    terminal = TERMINAL_RE.search(outcome)
    closed = bool(terminal) or bool(DONE_RE.search(outcome))
    # subject: the terminal line (marker + headline) if present, else the first non-empty line
    if terminal:
        subject = terminal.group(0).strip()
    else:
        subject = next((ln.strip() for ln in outcome.splitlines() if ln.strip()), "")[:200]
    return {
        "id": f"session:{sid}",
        "subject": subject[:200],
        "text": outcome[:4000],
        "repo": repo,
        "receipts": receipts,
        "closed": closed,
        "failed": bool(FAIL_RE.search(subject)),
    }


def _read_records(path: Path) -> list[dict]:
    out: list[dict] = []
    for ln in path.read_text(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _already_captured(sid: str) -> bool:
    if not LEDGER.exists():
        return False
    key = f"session:{sid}"
    for rec in _read_records(LEDGER):
        if rec.get("id") == key:
            return True
    return False


def _default_repo() -> str:
    """org/repo from the working checkout's origin, defaulting to organvm/limen."""
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5
        )
        m = re.search(r"github\.com[:/]([^/]+)/([^/.\s]+)", out.stdout)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return "organvm/limen"


def capture(sid: str, repo: str | None) -> int:
    """Append this session's closeout claim to the ledger. No-op (exit 0) on any miss — never
    blocks a session end."""
    path = _find_transcript(sid)
    if path is None:
        return 0
    if _already_captured(sid):
        return 0
    claim = extract_claim(_read_records(path), sid, repo or _default_repo())
    if claim is None:
        return 0
    claim["ts"] = datetime.now(timezone.utc).isoformat()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(claim) + "\n")
    return 0


def _doctor() -> int:
    """Network-free proof the extractor picks the right outcome, receipts, and closed-state."""
    ok = True

    def check(label: str, got, expected):
        nonlocal ok
        flag = "ok" if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"  [{flag}] {label}: expected {expected!r}, got {got!r}")

    def rec(text: str) -> dict:
        return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}

    # 1) terminal 'result:' line wins over a later plain narration, and its receipts are extracted
    c1 = extract_claim(
        [rec("mid narration"), rec("result: shipped the organ via PR #1211 (commit 361e6eff)"),
         rec("just a trailing note")],
        "s1", "organvm/limen",
    )
    check("c1.closed", c1["closed"], True)
    check("c1.receipts_has_pr", "PR #1211" in c1["receipts"] or any("1211" in r for r in c1["receipts"]), True)
    check("c1.subject_is_result", c1["subject"].lower().startswith("result:"), True)

    # 2) no terminal marker, no done-word → not closed (an unfinished session is never a claim)
    c2 = extract_claim([rec("still investigating the flaky test; nothing concluded yet")], "s2", "o/r")
    check("c2.closed", c2["closed"], False)

    # 3) a 'failed:' terminal is captured and flagged
    c3 = extract_claim([rec("failed: the binary is missing; cannot build")], "s3", "o/r")
    check("c3.closed", c3["closed"], True)
    check("c3.failed", c3["failed"], True)

    # 4) empty transcript → no claim
    check("c4.none", extract_claim([], "s4", "o/r"), None)

    # 5) a multiline message with a BLANK line before the terminal marker — the re.M `^\s*` trap:
    #    the subject must be the marker line itself, never an empty string swallowed from the newline.
    c5 = extract_claim([rec("Final state:\n\n```\nall green\n```\n\nresult: landed everything, PR #42 merged")],
                       "s5", "o/r")
    check("c5.subject_nonempty", bool(c5["subject"]), True)
    check("c5.subject_is_result", c5["subject"].lower().startswith("result:"), True)

    print("doctor: PASS" if ok else "doctor: FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="capture a session's closeout claim for reconciliation")
    ap.add_argument("--sid", help="session id (or transcript path)")
    ap.add_argument("--repo", help="org/repo the claim is about (default: origin of the checkout)")
    ap.add_argument("--doctor", action="store_true", help="network-free extractor self-test")
    args = ap.parse_args()

    if args.doctor:
        return _doctor()
    if not args.sid:
        ap.error("--sid is required (or --doctor)")
    return capture(args.sid, args.repo)


if __name__ == "__main__":
    sys.exit(main())
