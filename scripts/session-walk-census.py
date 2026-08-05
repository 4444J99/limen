#!/usr/bin/env python3
"""SESSION-WALK census — has every session been walked from first prompt to implementation?

Sweeps BOTH vendor session estates on this host:
  * Claude Code:  ~/.claude/projects/<proj>/<sid>.jsonl   (Claude Desktop's Code tab lists these)
  * Codex:        ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl  (Codex Desktop lists these)

Every session gets a terminal-state verdict:
  walked       — ends with a delivered closeout (terminal markers in the final assistant text)
  needs_input  — ends waiting on the human (a question / permission / "Want me to…")
  mid_flight   — ends on user or tool activity (the session died mid-work)
  dispatch     — a fleet dispatch/daemon run (board-owned lifecycle, not a user walk)
  empty        — no user prompt ever landed (noise)

The QUICKEN organ breathes the *recent* stalled tail (3-day horizon); this census is the
full-horizon completeness predicate behind "have ALL sessions been walked?" — the whole
estate, both vendors, all projects. Residue (needs_input + mid_flight user sessions) is
written to logs/session-walk-residue.md with a resume pointer per session so the walk is
executable, not prose.

Artifacts: logs/session-walk-census.json (+ voice stamp logs/.voice/session-walk).
--check exits 1 when user-session residue exists. Fail-open per file: an unreadable or
garbled transcript classifies as `unknown`, never crashes the sweep.

--walk N drains the residue: resumes the N newest unwalked sessions headlessly with the
QUICKEN guardrail prompt (reversible only — no push/send/delete/settings; edits confined
to an isolated worktree, never the live checkout). Each attempt is journaled in
logs/session-walk.jsonl; a session attempted LIMEN_SESSION_WALK_GIVE_UP (default 2) times
without leaving residue is skipped thereafter (it stays visible in the residue ledger for
the human). Codex resumes are current-local-day only unless this run carries an explicit
old-Codex override. Wired into the beat via metabolize.sh (LIMEN_SESSION_WALK gate), the
whole estate self-drains a few sessions per beat.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

HOME = Path.home()
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
LOGS = ROOT / "logs"

HEAD_BYTES = 96_000
TAIL_BYTES = 256_000

# Terminal-delivery markers in the FINAL assistant text — the session closed itself out.
WALKED_RX = re.compile(
    r"(^|\n)\s*result:|closeout complete|CLOSEOUT COMPLETE|fully done|"
    r"whole-system verification passed|nothing (left|remains) (open|dangling)|"
    r"idempotent fixed point",
    re.I,
)
# The session parked itself on the human.
NEEDS_RX = re.compile(
    r"needs input:|want me to\b|should i\b|shall i\b|let me know (which|if|how|when)|"
    r"waiting on (permission|your)|which (option|approach|one) (do you|would you)|\?\s*$",
    re.I,
)
DISPATCH_PROMPT_RX = re.compile(r"^\s*(Complete task |You are dispatched|\[dispatch\])")


def _read_edges(path: Path) -> tuple[list[str], list[str]]:
    """First/last JSONL lines without loading multi-MB transcripts whole."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(min(size, HEAD_BYTES)).decode("utf-8", errors="ignore")
        if size > HEAD_BYTES + TAIL_BYTES:
            fh.seek(size - TAIL_BYTES)
            tail = fh.read().decode("utf-8", errors="ignore")
            tail_lines = tail.splitlines()[1:]  # first line is likely truncated
        else:
            tail_lines = head.splitlines()
    return head.splitlines(), tail_lines


def _jloads(line: str):
    try:
        return json.loads(line)
    except Exception:
        return None


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def classify_claude(path: Path) -> dict:
    head, tail = _read_edges(path)
    first_prompt, cwd, sid = "", "", path.stem
    for ln in head:
        e = _jloads(ln)
        if not e:
            continue
        cwd = cwd or e.get("cwd") or ""
        if not first_prompt and e.get("type") == "user":
            t = _text_of((e.get("message") or {}).get("content"))
            if t and not t.startswith("<"):
                first_prompt = t.strip()[:160]
    last_role, last_asst_text = "", ""
    for ln in tail:
        e = _jloads(ln)
        if not e:
            continue
        t = e.get("type")
        if t == "assistant":
            txt = _text_of((e.get("message") or {}).get("content"))
            if txt.strip():
                last_asst_text = txt
            last_role = "assistant"
        elif t == "user":
            # tool_results ride user-typed lines; only real text counts as a human turn
            txt = _text_of((e.get("message") or {}).get("content"))
            last_role = "user" if txt.strip() else last_role
    if not first_prompt:
        verdict = "empty"
    elif DISPATCH_PROMPT_RX.search(first_prompt) or "/.limen-worktrees/" in cwd:
        verdict = "dispatch"
    elif last_role == "assistant" and WALKED_RX.search(last_asst_text or ""):
        verdict = "walked"
    elif last_role == "assistant" and NEEDS_RX.search((last_asst_text or "").strip()[-400:]):
        verdict = "needs_input"
    elif last_role == "assistant":
        verdict = "walked_soft"  # delivered a final message; no explicit closeout marker
    else:
        verdict = "mid_flight"
    return {
        "vendor": "claude",
        "sid": sid,
        "cwd": cwd,
        "purpose": first_prompt,
        "verdict": verdict,
        "mtime": int(path.stat().st_mtime),
        "resume": f"claude --resume {sid}",
    }


def classify_codex(path: Path) -> dict:
    head, tail = _read_edges(path)
    meta = next((e for e in (_jloads(x) for x in head) if e and e.get("type") == "session_meta"), None)
    payload = (meta or {}).get("payload") or {}
    sid = payload.get("id") or payload.get("session_id") or path.stem
    cwd = payload.get("cwd") or ""
    originator = payload.get("originator") or ""
    first_prompt = ""
    for ln in head:
        e = _jloads(ln)
        if not e:
            continue
        p = e.get("payload") or {}
        if e.get("type") == "event_msg" and p.get("type") == "user_message":
            first_prompt = str(p.get("message") or "")[:160]
            break
        if e.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "user":
            first_prompt = _text_of(p.get("content"))[:160] or first_prompt
            if first_prompt:
                break
    last_complete_msg, saw_complete = "", False
    for ln in tail:
        e = _jloads(ln)
        if not e:
            continue
        p = e.get("payload") or {}
        if e.get("type") == "event_msg" and p.get("type") == "task_complete":
            saw_complete = True
            last_complete_msg = str(p.get("last_agent_message") or "")
    if originator in ("codex_exec",) or "/.limen-worktrees/" in cwd:
        verdict = "dispatch"
    elif not first_prompt:
        verdict = "empty"
    elif saw_complete and NEEDS_RX.search(last_complete_msg.strip()[-400:]):
        verdict = "needs_input"
    elif saw_complete:
        verdict = "walked_soft" if not WALKED_RX.search(last_complete_msg) else "walked"
    else:
        verdict = "mid_flight"
    return {
        "vendor": "codex",
        "sid": sid,
        "cwd": cwd,
        "purpose": first_prompt,
        "verdict": verdict,
        "mtime": int(path.stat().st_mtime),
        "resume": f"codex exec resume {sid}",
    }


def sweep() -> list[dict]:
    rows: list[dict] = []
    claude_dir = HOME / ".claude" / "projects"
    for proj in sorted(claude_dir.iterdir()) if claude_dir.is_dir() else []:
        if not proj.is_dir() or proj.name == "memory":
            continue
        for f in proj.glob("*.jsonl"):
            try:
                rows.append(classify_claude(f))
            except Exception:
                rows.append(
                    {
                        "vendor": "claude",
                        "sid": f.stem,
                        "verdict": "unknown",
                        "cwd": "",
                        "purpose": "",
                        "mtime": 0,
                        "resume": "",
                    }
                )
    codex_dir = HOME / ".codex" / "sessions"
    if codex_dir.is_dir():
        for f in codex_dir.rglob("rollout-*.jsonl"):
            try:
                rows.append(classify_codex(f))
            except Exception:
                rows.append(
                    {
                        "vendor": "codex",
                        "sid": f.stem,
                        "verdict": "unknown",
                        "cwd": "",
                        "purpose": "",
                        "mtime": 0,
                        "resume": "",
                    }
                )
    return rows


WALK_PROMPT = (
    "Resume and FINISH your original purpose — you stalled and have been sitting. "
    "Decide every open step via the cascade: protocol dictates; else precedent; else explore to "
    "ideal-form certainty. Drive every REVERSIBLE step to completion now. PROTOCOL (hard): do NOT "
    "push/deploy (gate-hold), do NOT delete (archive reversibly), do NOT edit settings.json, do NOT "
    "send/email — stage or draft those instead. If your purpose is already complete, say so and "
    "close out. Surface only the single genuinely-irreducible human atom, one sentence, then stop. "
    "ADDITIONAL (hard): if your cwd is a shared/live checkout, never edit files there — create an "
    "isolated git worktree under .claude/worktrees/ and confine every edit to it. "
    "git add named files only; never git add -A."
)

WALK_JOURNAL = LOGS / "session-walk.jsonl"


def _walk_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        for ln in WALK_JOURNAL.read_text(errors="ignore").splitlines():
            try:
                e = json.loads(ln)
            except Exception:
                continue
            sid = e.get("walked")
            if sid:
                counts[sid] = counts.get(sid, 0) + 1
    except OSError:
        pass
    return counts


def local_day_start_ts(now: float | None = None) -> int:
    local = time.localtime(time.time() if now is None else now)
    return int(time.mktime((local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0, local.tm_wday, local.tm_yday, local.tm_isdst)))


def stale_codex_resume_blocked(row: dict, *, allow_old_codex_resume: bool = False, now: float | None = None) -> bool:
    if allow_old_codex_resume:
        return False
    if row.get("vendor") != "codex":
        return False
    return int(row.get("mtime") or 0) < local_day_start_ts(now)


def resume_display(row: dict, *, allow_old_codex_resume: bool = False, now: float | None = None) -> str:
    if stale_codex_resume_blocked(row, allow_old_codex_resume=allow_old_codex_resume, now=now):
        return "BLOCKED: stale Codex session; create a fresh bounded packet instead of resuming this session."
    return str(row.get("resume") or "")


def walk(residue: list[dict], cap: int, dry: bool, *, allow_old_codex_resume: bool = False) -> None:
    import subprocess

    give_up = int(os.environ.get("LIMEN_SESSION_WALK_GIVE_UP", "2"))
    timeout_s = int(os.environ.get("LIMEN_SESSION_WALK_TIMEOUT", "900"))
    counts = _walk_counts()
    eligible = []
    blocked = []
    for row in residue:
        if counts.get(row["sid"], 0) >= give_up:
            continue
        if stale_codex_resume_blocked(row, allow_old_codex_resume=allow_old_codex_resume):
            blocked.append(row)
            continue
        eligible.append(row)
    targets = eligible[:cap]
    print(f"[walk] {len(targets)} session(s) within cap={cap} (give_up={give_up})")
    for row in blocked:
        print(f"  SKIP stale codex {row['sid'][:8]}: fresh bounded packet required")
    for r in targets:
        cwd = r["cwd"] if r["cwd"] and Path(r["cwd"]).is_dir() else str(HOME)
        if r["vendor"] == "claude":
            cmd = ["claude", "--resume", r["sid"], "-p", WALK_PROMPT]
        else:
            cmd = ["codex", "exec", "resume", r["sid"], WALK_PROMPT]
        if dry:
            print(f"  DRY would walk {r['vendor']} {r['sid'][:8]} ({(r['purpose'] or '')[:48]})")
            continue
        print(f"  walking {r['vendor']} {r['sid'][:8]} ({(r['purpose'] or '')[:48]}) …")
        ok = False
        try:
            cp = subprocess.run(cmd, cwd=cwd, timeout=timeout_s, capture_output=True, text=True)
            ok = cp.returncode == 0
        except Exception as e:
            print(f"    walk failed: {e}")
        with WALK_JOURNAL.open("a") as fh:
            fh.write(json.dumps({"ts": int(time.time()), "walked": r["sid"], "vendor": r["vendor"], "ok": ok}) + "\n")
        print(f"    -> {'finished' if ok else 'errored'} (journaled)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if user-session residue exists")
    ap.add_argument("--residue-cap", type=int, default=int(os.environ.get("LIMEN_WALK_RESIDUE_CAP", "500")))
    ap.add_argument("--walk", type=int, default=0, metavar="N", help="resume the N newest residue sessions")
    ap.add_argument("--dry-walk", action="store_true", help="preview the walk without resuming")
    ap.add_argument(
        "--allow-old-codex-resume",
        action="store_true",
        help="explicit bounded-packet override for resuming Codex sessions older than the current local day",
    )
    args = ap.parse_args()

    rows = sweep()
    counts: dict[str, dict[str, int]] = {}
    for r in rows:
        counts.setdefault(r["vendor"], {}).setdefault(r["verdict"], 0)
        counts[r["vendor"]][r["verdict"]] += 1

    seen: set[str] = set()
    residue = []
    for r in sorted(
        (r for r in rows if r["verdict"] in ("needs_input", "mid_flight")),
        key=lambda r: -r["mtime"],
    ):
        if r["sid"] in seen:
            continue
        seen.add(r["sid"])
        residue.append(r)
    residue = residue[: args.residue_cap]

    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "session-walk-census.json").write_text(
        json.dumps({"generated": int(time.time()), "counts": counts, "residue": residue}, indent=1)
    )
    voice = LOGS / ".voice"
    voice.mkdir(parents=True, exist_ok=True)
    (voice / "session-walk").write_text(
        f"session-walk: {sum(v for c in counts.values() for v in c.values())} sessions, {len(residue)} residue\n"
    )
    md = ["# SESSION-WALK residue — unwalked user sessions (newest first)", ""]
    for r in residue:
        ts = time.strftime("%Y-%m-%d", time.localtime(r["mtime"]))
        md.append(f"- **{r['vendor']}** {ts} `{r['verdict']}` — {r['purpose'] or '(no title)'}")
        resume = resume_display(r, allow_old_codex_resume=args.allow_old_codex_resume)
        md.append(f"    `{resume}`   (cwd {r['cwd'] or '?'})")
    (LOGS / "session-walk-residue.md").write_text("\n".join(md) + "\n")

    print(json.dumps(counts, indent=1))
    print(f"residue: {len(residue)} unwalked user sessions -> logs/session-walk-residue.md")
    if args.walk:
        walk(residue, args.walk, dry=args.dry_walk, allow_old_codex_resume=args.allow_old_codex_resume)
    if args.check and residue:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
