#!/usr/bin/env python3
"""quicken.py — QUICKEN: give stalled sessions life so they finish their original purpose.

A session has a LIFECYCLE that ends in completion. A *working* session is alive and moving —
not our concern, hands off. A *sitting* session (awaiting-input, no movement) is stalled work
that stopped at its first question. The autonomic act is not to file it in a registry and stop
nagging — it is to BREATHE LIFE BACK IN so it finishes its purpose, advancing all the way up to
the single genuinely-irreducible human touch (and no further). Parking != closing.

The decision core is the cascade (his words, verbatim):
    protocol dictates the action
      -> if protocol fails, precedent suggests the action
        -> if protocol AND precedent fail, exploration ad infinitum
          -> until certainty arrives via ideal-form logic.
Protocols here are HARD invariants: gate-hold (no push/deploy), never auto-delete, never AI-edit
settings.json, never auto-send, confine edits to your own worktree when sessions are live,
reversible-first. A pending blocker that lands on a protocol-reserved lever IS the irreducible
human atom; everything around it is driveable.

GROUND TRUTH (no heuristic transcript scraping):
  * ~/.claude/projects/<projdir>/<sessionId>.jsonl  — FleetView stream: ai-title, last-prompt,
    permission-mode, plus conversation entries carrying cwd + timestamp (movement signal).
  * ~/.claude/tasks/<sessionId>/<n>.json            — the session's OWN todo list: each item
    {subject, description, status, blockedBy}. Purpose decomposed + completion state + the
    cascade decision often already recorded in the description ("HELD ...", "needs Maddie's
    decision", "resume only in a quiet window").

Anti-waste + never-"NO": read-only on every session's data; the default run only PRINTS the
lifecycle diagnosis. `--apply` writes only this organ's own journal (logs/session-lifecycle.jsonl)
and a deduped residue digest. The actual quickening (`--breathe`) resumes a stalled session
headlessly via `claude --resume <id> -p "<guardrailed continuation>"` — bounded, sequential,
worktree-contention-checked, and never fired against an ALIVE worktree or our own session. Every
probe fails OPEN: a missing/garbled file yields "unknown", never a crash.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"
TASKS = HOME / ".claude" / "tasks"
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
JOURNAL = ROOT / "logs" / "session-lifecycle.jsonl"
RESIDUE_OUT = ROOT / "docs" / "QUICKEN-RESIDUE.md"
# The PERMANENT home of a human atom is the running system's needs_human queue (surfaced by
# obligations-view / organ-health / reclassify), NOT a worktree doc. We hang residue there.
LEDGER = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
# atoms whose permanent home is a STANDING posture already hung once — never multiply into a task.
_POSTURE = {"push": "ASK-5-open-merge-gate (the standing gate-hold)"}

# A session idle longer than this (and with pending work) is STALLED, not "working".
STALE_MIN = int(os.environ.get("LIMEN_QUICKEN_STALE_MIN", "20"))
# Ignore FleetView sessions untouched for this many days (ancient/done history).
HORIZON_DAYS = int(os.environ.get("LIMEN_QUICKEN_HORIZON_DAYS", "3"))

# ── the cascade's protocol layer: a pending blocker matching one of these is an irreducible
#    human atom (his lever), NOT something to auto-do. Keyed signal -> cheapest-atom label. ──────
PROTOCOL = [
    ("settings",   re.compile(r"settings\.json|capture[- ]?hook|paste .*settings|proposed-?settings", re.I),
     "paste the staged settings.json proposal (AI self-edit of settings is hard-denied)"),
    ("login",      re.compile(r"setup-token|\bclaude (setup|/?login)\b|oauth login|set ?active|sign in|log ?in\b", re.I),
     "one login/identity step (your hand: browser/OAuth/portal)"),
    ("d2l",        re.compile(r"\bd2l\b|brightspace|set active|go-?live|cadence confirm", re.I),
     "the D2L go-live click + cadence confirm (your login + judgment)"),
    ("send",       re.compile(r"\bsend\b|\bemail\b|tell maddie|notify|announce|message the client|drip", re.I),
     "send the drafted message (never auto-send)"),
    ("delete",     re.compile(r"\bdelete\b|\bdrop \b|clear ~?/?downloads|\bwipe\b|\bpurge\b|rm -rf", re.I),
     "approve the irreversible delete/clear (archived reversibly; purge is yours)"),
    ("push",       re.compile(r"\bpush\b|\bdeploy\b|merge gate|ship to (main|prod|production)|open the gate", re.I),
     "open the gate to push/deploy (standing gate-hold)"),
    ("credential", re.compile(r"\bsecret\b|credential|api[ _-]?key|\btoken\b|password|gh secret set", re.I),
     "land the credential/secret (your account/identity)"),
]
# precedent layer: the session already RECORDED the decision in a todo description.
_PRECEDENT = re.compile(r"\bHELD\b|defer|on hold|resume only|awaiting|needs .* decision|blocked on|quiet window", re.I)
# a session whose last user prompt asked for a handoff/closeout has already wrapped its purpose.
_CLOSED = re.compile(r"prompt relay handoff|relay handoff|session report|full session report", re.I)
# idle longer than this (hours) -> already-wrapped history, not tonight's sitting work.
CLOSED_HRS = int(os.environ.get("LIMEN_QUICKEN_CLOSED_HRS", "18"))

# The guardrailed continuation injected to breathe a stalled session back to life. The cascade +
# protocol travel WITH the prompt so the resumed session finishes correctly, not blindly.
BREATHE_PROMPT = (
    "Resume and FINISH your original purpose — you stalled at a decision and have been sitting. "
    "Decide every open step via the cascade: protocol dictates; else precedent; else explore to "
    "ideal-form certainty. Drive every REVERSIBLE step to completion now. PROTOCOL (hard): do NOT "
    "push/deploy (gate-hold), do NOT delete (archive reversibly), do NOT edit settings.json, do NOT "
    "send/email — stage or draft those instead. If your purpose is already complete, say so and "
    "close out. Surface only the single genuinely-irreducible human atom (login / send / delete / "
    "settings-paste / gated-push), one sentence, then stop. Confine edits to THIS worktree+branch; "
    "git add named files only; never git add -A."
)


def _read_jsonl(path: Path):
    try:
        for ln in path.read_text(errors="ignore").splitlines():
            ln = ln.strip()
            if ln:
                try:
                    yield json.loads(ln)
                except Exception:
                    continue
    except OSError:
        return


def _decode_worktree(projdir: str) -> str:
    """Fallback worktree path from the encoded project-dir name. Lossy ('/' and '.' both -> '-'),
    so only used when the transcript carries no cwd."""
    s = projdir
    if s.startswith("-"):
        s = "/" + s[1:]
    return s.replace("--", "/.").replace("-", "/")  # best-effort; cwd from transcript preferred


def _enc(p: str) -> str:
    """Encode a path the way Claude names its project dirs: '.' and '/' both -> '-'."""
    return p.replace(".", "-").replace("/", "-")


def load_session(stream: Path) -> dict | None:
    sid = stream.stem
    title = last_prompt = perm = None
    cwds: list[str] = []
    has_title = False
    last_ts = 0.0
    for e in _read_jsonl(stream):
        t = e.get("type")
        if t == "ai-title":
            title = e.get("aiTitle") or title
            has_title = bool(title)
        elif t == "last-prompt":
            last_prompt = e.get("lastPrompt") or last_prompt
        elif t == "permission-mode":
            perm = e.get("permissionMode") or perm
        # conversation entries carry cwd + timestamp -> movement signal (cwd roams between trees)
        if e.get("cwd"):
            cwds.append(e["cwd"])
        ts = e.get("timestamp")
        if isinstance(ts, str):
            # ISO 8601 -> epoch, fail-open
            try:
                from datetime import datetime
                last_ts = max(last_ts, datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
    mtime = stream.stat().st_mtime if stream.exists() else 0.0
    move = max(last_ts, mtime)
    # CANONICAL resume dir = the cwd whose encoding matches the stream's project-dir name (that is
    # the tree `claude --resume` will find the session under). Roving cwds and the lossy decode are
    # only fallbacks — using the wrong one yields "No conversation found".
    proj = stream.parent.name
    cwd = next((c for c in cwds if _enc(c) == proj), None) or (cwds[-1] if cwds else _decode_worktree(proj))
    # A USER FleetView session has a human ai-title AND is not a daemon "Complete task <ID>"
    # dispatch run (those live under ~/Workspace/.limen-worktrees and have their own heal lifecycle).
    is_dispatch = (last_prompt or "").startswith("Complete task ") or "/.limen-worktrees/" in (cwd or "")
    return {
        "sessionId": sid, "title": title or sid[:8], "last_prompt": last_prompt or "",
        "perm": perm or "?", "cwd": cwd, "moved": move, "stream": str(stream),
        "fleetview": bool(has_title) and not is_dispatch,
    }


def load_todos(sid: str) -> list[dict]:
    d = TASKS / sid
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            j = json.loads(f.read_text())
            out.append({"subject": j.get("subject", ""), "status": j.get("status", "?"),
                        "desc": j.get("description", ""), "blockedBy": j.get("blockedBy", [])})
        except Exception:
            continue
    return out


def classify_state(sess: dict, todos: list[dict], now: float) -> str:
    idle_min = (now - sess["moved"]) / 60.0 if sess["moved"] else 1e9
    pending = [t for t in todos if t["status"] in ("pending", "in_progress")]
    if idle_min < STALE_MIN:
        return "ALIVE"         # moving — hands off (errs safe: mtime >= last msg)
    if todos and not pending:
        return "DONE"          # purpose complete
    if _CLOSED.search(sess["last_prompt"]) or idle_min > CLOSED_HRS * 60:
        return "CLOSED"        # already wrapped (handoff/report) or old history
    return "STALLED"


def cascade_decide(sess: dict, todos: list[dict]) -> dict:
    """Run the pending work through protocol -> precedent -> (explore) -> ideal-form.
    Returns {layer, action, residue}. residue is the single irreducible human atom (or None)."""
    pending = [t for t in todos if t["status"] in ("pending", "in_progress")]
    blob = " ".join([sess["title"], sess["last_prompt"]] + [f"{t['subject']} {t['desc']}" for t in pending])

    # protocol: does the blocker land on a reserved human lever?
    residue = None
    for _key, rx, atom in PROTOCOL:
        if rx.search(blob):
            residue = atom
            break

    # precedent: did the session already record the decision (HELD/defer/needs-X-decision)?
    recorded = bool(_PRECEDENT.search(blob))

    if residue and recorded:
        layer = "protocol+precedent"
        action = "drive every reversible step to done; the decision is already recorded; surface ONE atom"
    elif residue:
        layer = "protocol"
        action = "drive every reversible step to done up to the lever; stage/draft; surface ONE atom"
    elif recorded:
        layer = "precedent"
        action = "apply the recorded decision and finish the purpose (reversible only)"
    elif pending or sess["last_prompt"]:
        layer = "ideal-form"
        action = "resume the session to finish its purpose (reversible only; no push/delete/settings/send)"
    else:
        layer = "explore"
        action = "explore the session to recover its next step, then finish"
    return {"layer": layer, "action": action, "residue": residue, "recorded": recorded,
            "n_pending": len(pending), "n_done": len([t for t in todos if t["status"] == "completed"])}


def gather(now: float, self_sid: str | None) -> list[dict]:
    rows = []
    if not PROJECTS.is_dir():
        return rows
    horizon = now - HORIZON_DAYS * 86400
    for stream in PROJECTS.glob("*/*.jsonl"):
        try:
            if stream.stat().st_mtime < horizon:
                continue
        except OSError:
            continue
        sess = load_session(stream)
        if not sess:
            continue
        # only USER FleetView sessions — fleet dispatch task-runs heal via heal-dispatch.py
        if not sess["fleetview"]:
            continue
        todos = load_todos(sess["sessionId"])
        sess["state"] = classify_state(sess, todos, now)
        sess["todos"] = todos
        sess["decision"] = cascade_decide(sess, todos)
        sess["is_self"] = (sess["sessionId"] == self_sid)
        rows.append(sess)
    # dedupe by title — multiple resumed instances of one logical session show as one row
    # (FleetView shows one). Keep the most-recently-moved; count the superseded.
    best: dict[str, dict] = {}
    for r in rows:
        key = r["title"]
        if key not in best or r["moved"] > best[key]["moved"]:
            if key in best:
                r["superseded"] = best[key].get("superseded", 0) + 1
            best[key] = r
        else:
            best[key]["superseded"] = best[key].get("superseded", 0) + 1
    rows = sorted(best.values(), key=lambda r: r["moved"], reverse=True)
    return rows


def fmt_report(rows: list[dict]) -> str:
    states = {}
    for r in rows:
        states.setdefault(r["state"], []).append(r)
    out = [f"# QUICKEN — session lifecycle  ({len(rows)} sessions, stale>{STALE_MIN}m, horizon {HORIZON_DAYS}d)", ""]
    for st in ("STALLED", "ALIVE", "DONE", "CLOSED"):
        bucket = states.get(st, [])
        out.append(f"## {st} — {len(bucket)}")
        for r in bucket:
            idle = (time.time() - r["moved"]) / 60.0 if r["moved"] else -1
            mark = " (self)" if r["is_self"] else ""
            sup = f" +{r['superseded']} superseded" if r.get("superseded") else ""
            d = r["decision"]
            out.append(f"- **{r['title'][:54]}**{mark}  ·  idle {idle:.0f}m  ·  {d['n_done']}✓/{d['n_pending']}⏳{sup}")
            if st == "STALLED":
                out.append(f"    cascade[{d['layer']}]: {d['action']}")
                if d["residue"]:
                    out.append(f"    → irreducible atom: {d['residue']}")
                if r["last_prompt"]:
                    out.append(f"    last-prompt: \"{r['last_prompt'][:80]}\"")
                out.append(f"    resume: claude --resume {r['sessionId']} -p '<continuation>'   (cwd {r['cwd']})")
        out.append("")
    return "\n".join(out)


def _atom_key(atom: str) -> str:
    """The PROTOCOL key that produced this atom (stable id namespace), or 'misc'."""
    return next((k for k, _rx, a in PROTOCOL if a == atom), "misc")


def hang_residue(rows: list[dict]) -> dict:
    """Hang each irreducible human atom in the PERMANENT needs_human queue — the running system of
    record (obligations-view / organ-health / reclassify all read it), capture-pushed off-disk — so
    no obligation ever lives only in a disposable worktree doc. Idempotent within QUICKEN's own
    `ASK-quicken-<key>` namespace; written under the shared queue-lock via the atomic primitive so a
    concurrent heartbeat can never see a torn queue. Posture atoms (gate-hold) are already homed once
    and are never multiplied. Fail-open: a lock miss skips this beat and self-corrects next."""
    by_key: dict[str, dict] = {}
    for r in rows:
        if r["state"] != "STALLED" or not r["decision"]["residue"]:
            continue
        atom = r["decision"]["residue"]
        k = _atom_key(atom)
        by_key.setdefault(k, {"atom": atom, "unblocks": set()})["unblocks"].add(r["title"][:48])
    res = {"created": [], "refreshed": [], "homed": [], "ledger": str(LEDGER)}
    if not by_key:
        return res
    try:
        sys.path.insert(0, str(ROOT / "cli" / "src"))
        from datetime import date, datetime, timezone
        from limen.io import load_limen_file, queue_lock, save_limen_file
        from limen.models import Task
    except Exception as e:  # never dead-stop the apply if the cli pkg isn't importable
        res["error"] = f"ledger unavailable ({e}); residue digest still written"
        return res
    if not LEDGER.exists():
        res["error"] = f"no ledger at {LEDGER}; residue digest still written"
        return res
    with queue_lock(LEDGER) as got:
        if not got:
            res["error"] = "queue busy; skipped this beat (self-corrects)"
            return res
        lf = load_limen_file(LEDGER)
        index = {t.id: t for t in lf.tasks}
        now = datetime.now(timezone.utc)
        for k, info in sorted(by_key.items()):
            if k in _POSTURE:
                res["homed"].append(f"{info['atom']} → {_POSTURE[k]}")
                continue
            tid = f"ASK-quicken-{k}"
            ctx = (f"Cheapest path → {info['atom']}. Unblocks: {', '.join(sorted(info['unblocks']))}. "
                   f"Auto-hung by QUICKEN (finish-not-park); refreshes each beat until you act.")
            ex = index.get(tid)
            if ex and ex.status != "done":
                ex.status, ex.context, ex.updated = "needs_human", ctx, now
                if "quicken-residue" not in (ex.labels or []):
                    ex.labels = list(ex.labels or []) + ["quicken-residue"]
                res["refreshed"].append(tid)
            elif ex is None:
                lf.tasks.append(Task(
                    id=tid, title=info["atom"], type="ops", target_agent="human",
                    priority="high", status="needs_human",
                    labels=["user-ask", "quicken-residue", "needs-human"],
                    context=ctx, created=date.today(), updated=now))
                res["created"].append(tid)
        save_limen_file(LEDGER, lf)
    return res


def write_residue(rows: list[dict]) -> str:
    """The deduped irreducible residue — surfaced ONLY after driving to completion, never as a
    substitute for finishing. One line per genuinely-human atom, deduped across sessions."""
    atoms: dict[str, list[str]] = {}
    for r in rows:
        if r["state"] == "STALLED" and r["decision"]["residue"]:
            atoms.setdefault(r["decision"]["residue"], []).append(r["title"][:48])
    lines = ["# QUICKEN residue — the irreducible human atoms (deduped)", "",
             "> A VIEW, not the home. Each atom is hung in the PERMANENT `needs_human` queue as",
             "> `ASK-quicken-<key>` (surfaced by obligations-view / organ-health / reclassify,",
             "> capture-pushed off-disk) — so nothing waits in a disposable doc. Owner of every",
             "> atom: you (identity / login / send / physical / gate). Everything else is",
             "> daemon-owned and fires each beat; it is not hanging.", ""]
    for atom, titles in sorted(atoms.items()):
        home = _POSTURE.get(_atom_key(atom)) or f"`ASK-quicken-{_atom_key(atom)}` (needs_human)"
        lines.append(f"- **{atom}**  ·  owner: **you**  ·  hung: {home}  ·  "
                     f"unblocks: {', '.join(sorted(set(titles)))}")
    if not atoms:
        lines.append("- (none — every stalled purpose was fully driveable; nothing waits on you)")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="QUICKEN — finish stalled sessions' purposes")
    ap.add_argument("--apply", action="store_true",
                    help="write the lifecycle journal + deduped residue digest (no session is resumed)")
    ap.add_argument("--breathe", metavar="SID|all", default=None,
                    help="resume stalled session(s) headlessly with a guardrailed continuation (bounded by cap)")
    ap.add_argument("--dry-breathe", action="store_true",
                    help="with --breathe: print which sessions WOULD be breathed, fire nothing")
    ap.add_argument("--self", dest="self_sid", default=os.environ.get("CLAUDE_SESSION_ID"),
                    help="our own session id — never acted upon")
    args = ap.parse_args()

    now = time.time()
    rows = gather(now, args.self_sid)
    print(fmt_report(rows))

    if args.apply or args.breathe:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": int(now), "sessions": len(rows),
               "stalled": [r["sessionId"] for r in rows if r["state"] == "STALLED"],
               "alive": [r["sessionId"] for r in rows if r["state"] == "ALIVE"],
               "done": [r["sessionId"] for r in rows if r["state"] == "DONE"]}
        with JOURNAL.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        RESIDUE_OUT.parent.mkdir(parents=True, exist_ok=True)
        RESIDUE_OUT.write_text(write_residue(rows))
        print(f"\n[apply] journal+residue written -> {JOURNAL.name}, {RESIDUE_OUT.name}")
        # hang each atom in the PERMANENT needs_human queue — the running system holds it, not a doc.
        h = hang_residue(rows)
        bits = []
        if h["created"]:   bits.append(f"created {', '.join(h['created'])}")
        if h["refreshed"]: bits.append(f"refreshed {', '.join(h['refreshed'])}")
        if h["homed"]:     bits.append(f"already-homed {len(h['homed'])}")
        if h.get("error"): bits.append(h["error"])
        print(f"[apply] permanent ledger ({Path(h['ledger']).name}): "
              f"{'; '.join(bits) or 'no residue to hang'}")

    if args.breathe:
        breathe(rows, args.breathe, dry=args.dry_breathe)
    return 0


# worktrees we never reach into: the contended live checkout (shared with the daemon) and any
# tree currently hosting an ALIVE session (avoid colliding with moving work).
def _contended(cwd: str, alive_cwds: set[str]) -> bool:
    limen = str(ROOT).split("/.claude/worktrees/")[0]
    if cwd in (limen, str(ROOT)) or cwd in alive_cwds:
        return True                                  # live checkout / a moving session's tree
    if "/.claude/projects/" in cwd or not Path(cwd).is_dir():
        return True                                  # not a real, present worktree → don't reach in
    return False


def breathe(rows: list[dict], sel: str, dry: bool) -> None:
    import subprocess
    cap = int(os.environ.get("LIMEN_QUICKEN_BREATHE_CAP", "1"))     # bounded-work contract: small
    to = int(os.environ.get("LIMEN_QUICKEN_BREATHE_TIMEOUT", "900"))
    # `all` breathes only STALLED (never auto-touch a moving session); a NAMED sid is an explicit
    # choice — honor it regardless of the flickery ALIVE/STALLED label (still skip contended trees).
    targets = [r for r in rows if not r["is_self"]
               and (r["sessionId"] == sel if sel != "all" else r["state"] == "STALLED")]
    # contention = ANOTHER moving session shares the tree; a session never self-contends.
    def _others(sid):
        return {r["cwd"] for r in rows if r["state"] == "ALIVE" and r["sessionId"] != sid}
    targets = [r for r in targets if not _contended(r["cwd"], _others(r["sessionId"]))]
    targets.sort(key=lambda r: r["moved"])                          # oldest-stalled first
    targets = targets[:cap]
    print(f"\n[breathe] {len(targets)} session(s) within cap={cap}; contended/ALIVE worktrees skipped.")
    for r in targets:
        cmd = ["claude", "--resume", r["sessionId"], "-p", BREATHE_PROMPT]
        if dry:
            print(f"  DRY would breathe {r['sessionId']} ({r['title'][:38]}) in {r['cwd']}")
            continue
        print(f"  breathing {r['sessionId']} ({r['title'][:38]}) …")
        try:
            cp = subprocess.run(cmd, cwd=r["cwd"], timeout=to, capture_output=True, text=True)
            ok = cp.returncode == 0
        except Exception as e:
            ok = False
            print(f"    breathe failed: {e}")
        with JOURNAL.open("a") as fh:
            fh.write(json.dumps({"ts": int(time.time()), "breathed": r["sessionId"],
                                 "title": r["title"][:60], "ok": bool(ok)}) + "\n")
        print(f"    -> {'finished' if ok else 'errored'} (journaled)")


if __name__ == "__main__":
    raise SystemExit(main())
