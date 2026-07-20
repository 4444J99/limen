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

# ── the CLOSEOUT ritual, autonomic: a finished session leaves a spent isolation worktree behind.
#    QUICKEN identifies those roots, but terminal removal is delegated to the acceptance-gated
#    worktree/branch reapers so archive + redaction proof stay in the shared covenant. ───────────────
WORKTREE_MARKERS = ("/.claude/worktrees/", "/.worktrees/", "/.limen-worktrees/")
# SessionEnd hook drops a breadcrumb here so a deliberately-ended session is classified on the NEXT beat
# instead of waiting out CLOSED_HRS. Removal stays with the acceptance-gated reaper organs.
CLOSEOUT_LOG = ROOT / "logs" / "session-closeout.jsonl"
# the candidate detector is ON by default; physical removal is not performed here.
REAP_ON = os.environ.get("LIMEN_QUICKEN_REAP", "1") == "1"


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# A session idle longer than this (and with pending work) is STALLED, not "working".
STALE_MIN = positive_int_env("LIMEN_QUICKEN_STALE_MIN", 20)
# Ignore FleetView sessions untouched for this many days (ancient/done history).
HORIZON_DAYS = positive_int_env("LIMEN_QUICKEN_HORIZON_DAYS", 3)

# ── the cascade's protocol layer: a pending blocker matching one of these is an irreducible
#    human atom (his lever), NOT something to auto-do. Keyed signal -> cheapest-atom label. ──────
PROTOCOL = [
    (
        "settings",
        re.compile(r"settings\.json|capture[- ]?hook|paste .*settings|proposed-?settings", re.I),
        "paste the staged settings.json proposal (AI self-edit of settings is hard-denied)",
    ),
    (
        "login",
        re.compile(r"setup-token|\bclaude (setup|/?login)\b|oauth login|set ?active|sign in|log ?in\b", re.I),
        "one login/identity step (your hand: browser/OAuth/portal)",
    ),
    (
        "d2l",
        re.compile(r"\bd2l\b|brightspace|set active|go-?live|cadence confirm", re.I),
        "the D2L go-live click + cadence confirm (your login + judgment)",
    ),
    (
        "send",
        re.compile(r"\bsend\b|\bemail\b|tell maddie|notify|announce|message the client|drip", re.I),
        "send the drafted message (never auto-send)",
    ),
    (
        "delete",
        re.compile(r"\bdelete\b|\bdrop \b|clear ~?/?downloads|\bwipe\b|\bpurge\b|rm -rf", re.I),
        "approve the irreversible delete/clear (archived reversibly; purge is yours)",
    ),
    (
        "push",
        re.compile(r"\bpush\b|\bdeploy\b|merge gate|ship to (main|prod|production)|open the gate", re.I),
        "open the gate to push/deploy (standing gate-hold)",
    ),
    (
        "credential",
        re.compile(r"\bsecret\b|credential|api[ _-]?key|\btoken\b|password|gh secret set", re.I),
        "land the credential/secret (your account/identity)",
    ),
]
# precedent layer: the session already RECORDED the decision in a todo description.
_PRECEDENT = re.compile(r"\bHELD\b|defer|on hold|resume only|awaiting|needs .* decision|blocked on|quiet window", re.I)
# a session whose last user prompt asked for a handoff/closeout has already wrapped its purpose.
_CLOSED = re.compile(r"prompt relay handoff|relay handoff|session report|full session report", re.I)
# idle longer than this (hours) -> already-wrapped history, not tonight's sitting work.
CLOSED_HRS = positive_int_env("LIMEN_QUICKEN_CLOSED_HRS", 18)

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
        "sessionId": sid,
        "title": title or sid[:8],
        "last_prompt": last_prompt or "",
        "perm": perm or "?",
        "cwd": cwd,
        "moved": move,
        "stream": str(stream),
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
            out.append(
                {
                    "subject": j.get("subject", ""),
                    "status": j.get("status", "?"),
                    "desc": j.get("description", ""),
                    "blockedBy": j.get("blockedBy", []),
                }
            )
        except Exception:
            continue
    return out


def classify_state(sess: dict, todos: list[dict], now: float) -> str:
    idle_min = (now - sess["moved"]) / 60.0 if sess["moved"] else 1e9
    pending = [t for t in todos if t["status"] in ("pending", "in_progress")]
    if idle_min < STALE_MIN:
        return "ALIVE"  # moving — hands off (errs safe: mtime >= last msg)
    if todos and not pending:
        return "DONE"  # purpose complete
    if _CLOSED.search(sess["last_prompt"]) or idle_min > CLOSED_HRS * 60:
        return "CLOSED"  # already wrapped (handoff/report) or old history
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
    return {
        "layer": layer,
        "action": action,
        "residue": residue,
        "recorded": recorded,
        "n_pending": len(pending),
        "n_done": len([t for t in todos if t["status"] == "completed"]),
    }


def _ended_sids() -> set[str]:
    """Sessions the SessionEnd hook marked as deliberately ended → CLOSED now, not after CLOSED_HRS.
    Fail-open: a missing/garbled breadcrumb log just yields the empty set (timing falls back to idle)."""
    out: set[str] = set()
    for e in _read_jsonl(CLOSEOUT_LOG):
        sid = e.get("sid")
        if sid:
            out.add(sid)
    return out


def gather(now: float, self_sid: str | None) -> list[dict]:
    rows = []
    if not PROJECTS.is_dir():
        return rows
    ended = _ended_sids()
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
        # a deliberately-ended (ctrl+x'd) session is CLOSED immediately — reap-eligible without the
        # 18h idle wait — unless it is still genuinely moving (errs safe: never reap an ALIVE tree).
        if sess["sessionId"] in ended and sess["state"] != "ALIVE":
            sess["state"] = "CLOSED"
        sess["todos"] = todos
        sess["decision"] = cascade_decide(sess, todos)
        sess["is_self"] = sess["sessionId"] == self_sid
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
    counts = _breathe_counts()
    escalate_after = positive_int_env("LIMEN_QUICKEN_ESCALATE_AFTER", 2)
    out = [f"# QUICKEN — session lifecycle  ({len(rows)} sessions, stale>{STALE_MIN}m, horizon {HORIZON_DAYS}d)", ""]
    for st in ("STALLED", "ALIVE", "DONE", "CLOSED"):
        bucket = states.get(st, [])
        out.append(f"## {st} — {len(bucket)}")
        for r in bucket:
            idle = (time.time() - r["moved"]) / 60.0 if r["moved"] else -1
            mark = " (self)" if r["is_self"] else ""
            sup = f" +{r['superseded']} superseded" if r.get("superseded") else ""
            n = counts.get(r["sessionId"], 0)
            br = ""
            if st == "STALLED" and n:
                br = f"  ·  breathed {n}x" + ("  ·  ESCALATES" if n >= escalate_after else "")
            d = r["decision"]
            out.append(
                f"- **{r['title'][:54]}**{mark}  ·  idle {idle:.0f}m  ·  {d['n_done']}✓/{d['n_pending']}⏳{sup}{br}"
            )
            if st == "STALLED":
                out.append(f"    cascade[{d['layer']}]: {d['action']}")
                if d["residue"]:
                    out.append(f"    → irreducible atom: {d['residue']}")
                if r["last_prompt"]:
                    out.append(f'    last-prompt: "{r["last_prompt"][:80]}"')
                out.append(f"    resume: claude --resume {r['sessionId']} -p '<continuation>'   (cwd {r['cwd']})")
        out.append("")
    return "\n".join(out)


def _atom_key(atom: str) -> str:
    """The PROTOCOL key that produced this atom (stable id namespace), or 'misc'."""
    return next((k for k, _rx, a in PROTOCOL if a == atom), "misc")


def _split_unblocks(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _queue_residue_atoms() -> dict[str, list[str]]:
    """Residue already hung in tasks.yaml must stay visible in the digest."""
    atoms: dict[str, list[str]] = {}
    try:
        sys.path.insert(0, str(ROOT / "cli" / "src"))
        from limen.io import load_limen_file
    except Exception:
        return atoms
    if not LEDGER.exists():
        return atoms
    try:
        lf = load_limen_file(LEDGER)
    except Exception:
        return atoms
    for task in lf.tasks:
        labels = set(task.labels or [])
        if task.status != "needs_human":
            continue
        if not (task.id.startswith("ASK-quicken-") or "quicken-residue" in labels):
            continue
        atom = (task.title or task.id).strip()
        if not atom:
            continue
        unblocks = "permanent queue"
        if task.context:
            match = re.search(r"Unblocks: ([^.]+)", task.context)
            if match:
                unblocks = match.group(1).strip()
        for title in _split_unblocks(unblocks):
            atoms.setdefault(atom, []).append(title[:48])
    return atoms


def _hang_asks(entries: list[dict]) -> dict:
    """Upsert `ASK-*` needs_human tasks in the PERMANENT queue — the running system of record
    (obligations-view / organ-health / reclassify all read it), capture-pushed off-disk — so no
    obligation ever lives only in a disposable worktree doc. Each entry: {tid, title, context,
    labels}. Idempotent per tid; written under the shared queue-lock via the atomic primitive so a
    concurrent heartbeat can never see a torn queue. Fail-open: a lock miss skips this beat and
    self-corrects next."""
    res = {"created": [], "refreshed": [], "homed": [], "ledger": str(LEDGER)}
    if not entries:
        return res
    try:
        sys.path.insert(0, str(ROOT / "cli" / "src"))
        from datetime import date, datetime, timezone
        from limen.io import load_limen_file, queue_lock
        from limen.intake import contract_fields, github_issue_owner_contract
        from limen.models import Task, has_jules_landing_hold
        from limen.tabularius import apply_limen_file_sync
        from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL
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
        changed = False
        for entry in entries:
            tid = entry["tid"]
            contract = contract_fields(github_issue_owner_contract("organvm/limen", tid))
            ex = index.get(tid)
            if (
                ex
                and ex.status != "done"
                and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL not in (ex.labels or [])
                and not has_jules_landing_hold(ex)
            ):
                refreshed = False
                if ex.status != "needs_human":
                    ex.status = "needs_human"
                    refreshed = True
                if ex.context != entry["context"]:
                    ex.context = entry["context"]
                    refreshed = True
                if "quicken-residue" not in (ex.labels or []):
                    ex.labels = list(ex.labels or []) + ["quicken-residue"]
                    refreshed = True
                if refreshed:
                    ex.updated = now
                    changed = True
                    res["refreshed"].append(tid)
                else:
                    res["homed"].append(f"{entry['title']} → {tid}")
            elif ex is None:
                lf.tasks.append(
                    Task(
                        id=tid,
                        title=entry["title"],
                        repo="organvm/limen",
                        type="ops",
                        target_agent="human",
                        priority="high",
                        status="needs_human",
                        labels=entry["labels"],
                        context=entry["context"],
                        **contract,
                        created=date.today(),
                        updated=now,
                    )
                )
                changed = True
                res["created"].append(tid)
        if changed:
            apply_limen_file_sync(LEDGER, lf, agent="quicken", session_id="hang-asks")
    return res


def hang_residue(rows: list[dict]) -> dict:
    """Hang each irreducible human atom as `ASK-quicken-<key>` via _hang_asks. Posture atoms
    (gate-hold) are already homed once and are never multiplied."""
    by_key: dict[str, dict] = {}
    for r in rows:
        if r["state"] != "STALLED" or not r["decision"]["residue"]:
            continue
        atom = r["decision"]["residue"]
        k = _atom_key(atom)
        by_key.setdefault(k, {"atom": atom, "unblocks": set()})["unblocks"].add(r["title"][:48])
    entries = []
    homed_postures = []
    for k, info in sorted(by_key.items()):
        if k in _POSTURE:
            homed_postures.append(f"{info['atom']} → {_POSTURE[k]}")
            continue
        entries.append(
            {
                "tid": f"ASK-quicken-{k}",
                "title": info["atom"],
                "labels": ["user-ask", "quicken-residue", "needs-human"],
                "context": (
                    f"Cheapest path → {info['atom']}. Unblocks: {', '.join(sorted(info['unblocks']))}. "
                    f"Auto-hung by QUICKEN (finish-not-park); refreshes each beat until you act."
                ),
            }
        )
    res = _hang_asks(entries)
    res["homed"] = homed_postures + res["homed"]
    return res


def write_residue(rows: list[dict]) -> str:
    """The deduped irreducible residue — surfaced ONLY after driving to completion, never as a
    substitute for finishing. One line per genuinely-human atom, deduped across sessions."""
    atoms: dict[str, list[str]] = {}
    for r in rows:
        if r["state"] == "STALLED" and r["decision"]["residue"]:
            atoms.setdefault(r["decision"]["residue"], []).append(r["title"][:48])
    for atom, titles in _queue_residue_atoms().items():
        for title in titles:
            atoms.setdefault(atom, []).extend(t[:48] for t in _split_unblocks(title))
    lines = [
        "# QUICKEN residue — the irreducible human atoms (deduped)",
        "",
        "> A VIEW, not the home. Each atom is hung in the PERMANENT `needs_human` queue as",
        "> `ASK-quicken-<key>` (surfaced by obligations-view / organ-health / reclassify,",
        "> capture-pushed off-disk) — so nothing waits in a disposable doc. Owner of every",
        "> atom: you (identity / login / send / physical / gate). Everything else is",
        "> daemon-owned and fires each beat; it is not hanging.",
        "",
    ]
    for atom, titles in sorted(atoms.items()):
        home = _POSTURE.get(_atom_key(atom)) or f"`ASK-quicken-{_atom_key(atom)}` (needs_human)"
        lines.append(f"- **{atom}**  ·  owner: **you**  ·  hung: {home}  ·  unblocks: {', '.join(sorted(set(titles)))}")
    if not atoms:
        lines.append("- (none — every stalled purpose was fully driveable; nothing waits on you)")
    return "\n".join(lines) + "\n"


def _git(cwd: str, *args: str) -> tuple[int, str, str]:
    """git -C cwd … , fail-open: any exception → (1, '', msg). Bounded, offline (no fetch)."""
    import subprocess

    try:
        cp = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=30)
        return cp.returncode, cp.stdout.strip(), cp.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def _gh_merged(cwd: str, branch: str) -> bool:
    """Does a MERGED PR exist for this branch? Last-resort merge proof for squash merges whose
    patch-ids drifted during conflict resolution. Fail-open: any error → False (don't reap)."""
    import subprocess

    try:
        cp = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "number", "-q", ".[].number"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return cp.returncode == 0 and bool(cp.stdout.strip())
    except Exception:
        return False


def _branch_merged(cwd: str, branch: str) -> tuple[bool, str]:
    """VERIFIED-merged = safe to reap. Handles fast-forward AND squash/rebase (where SHAs differ) —
    the exact guard memory says to run before any worktree-remove / branch -D. Fail CLOSED: any
    uncertainty returns (False, why) so an unmerged branch is NEVER reaped."""
    rc, ahead, _ = _git(cwd, "rev-list", "--count", f"origin/main..{branch}")
    if rc == 0 and ahead == "0":
        return True, "0 commits ahead of origin/main"
    # squash/rebase: git cherry marks '+' for any commit whose patch is NOT yet upstream.
    rc, out, _ = _git(cwd, "cherry", "origin/main", branch)
    if rc == 0 and not any(ln.startswith("+") for ln in out.splitlines()):
        return True, "all commits patch-present in origin/main (squash/rebase)"
    if _gh_merged(cwd, branch):
        return True, "a merged PR exists for this branch"
    return False, "commits unique to branch — NOT verified-merged"


def reap_done(rows: list[dict], self_cwd: str, apply: bool) -> dict:
    """The CLOSEOUT ritual, autonomic. A session whose purpose is finished (DONE) or that was
    deliberately ended (CLOSED) leaves a spent isolation worktree behind; identify its terminal
    removal packet — but ONLY when verified safe on every axis:
      * the cwd is an isolation worktree (never a clone or the live main checkout);
      * not our own / a live / a contended tree (errs safe — skip on any doubt);
      * the tree is CLEAN — fail closed on a single uncommitted byte;
      * the branch is VERIFIED fully-merged into origin/main (see _branch_merged).
    Physical removal is delegated to reclaim-worktrees.py and reap-branches.py, whose acceptance
    ledgers require archive/redaction proof. Fail-open: any error leaves the tree intact and never
    crashes the beat. Without `apply` it only previews (no mutation)."""
    res = {"reaped": [], "kept": [], "would": [], "delegated": [], "on": REAP_ON}
    if not REAP_ON:
        return res
    alive = {r["cwd"] for r in rows if r["state"] == "ALIVE"}
    live_main = str(ROOT).split("/.claude/worktrees/")[0]
    for r in rows:
        if r["state"] not in ("DONE", "CLOSED"):
            continue
        cwd = r["cwd"] or ""
        title = r["title"][:40]
        if not any(m in cwd for m in WORKTREE_MARKERS):
            continue  # only spent isolation worktrees
        if r["is_self"] or cwd in (self_cwd, live_main, str(ROOT)) or cwd in alive:
            continue  # live / self / contended — never reap
        if not Path(cwd).is_dir():
            continue  # already gone
        rc, st, _ = _git(cwd, "status", "--porcelain")
        if rc != 0 or st:
            res["kept"].append((title, "uncommitted changes"))
            continue
        rc, branch, _ = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
        if rc != 0 or branch in ("", "HEAD", "main", "master"):
            res["kept"].append((title, f"unsafe branch ref ({branch or 'detached'})"))
            continue
        merged, why = _branch_merged(cwd, branch)
        if not merged:
            res["kept"].append((title, why))
            continue
        if not apply:
            res["would"].append((title, branch, why))
            continue
        res["delegated"].append((title, branch, why))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="QUICKEN — finish stalled sessions' purposes")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="write the lifecycle journal + deduped residue digest (no session is resumed)",
    )
    ap.add_argument(
        "--breathe",
        metavar="SID|all",
        default=None,
        help="resume stalled session(s) headlessly with a guardrailed continuation (bounded by cap)",
    )
    ap.add_argument(
        "--dry-breathe",
        action="store_true",
        help="with --breathe: print which sessions WOULD be breathed, fire nothing",
    )
    ap.add_argument(
        "--self",
        dest="self_sid",
        default=os.environ.get("CLAUDE_SESSION_ID"),
        help="our own session id — never acted upon",
    )
    args = ap.parse_args()

    now = time.time()
    rows = gather(now, args.self_sid)
    print(fmt_report(rows))

    # CLOSEOUT — reap spent, verified-merged isolation worktrees (preview unless --apply).
    reap = reap_done(rows, os.getcwd(), apply=args.apply)
    if not reap["on"]:
        print("\n[reap] disabled (LIMEN_QUICKEN_REAP=0)")
    elif reap["reaped"]:
        for t, b, why in reap["reaped"]:
            print(f"[reap] removed worktree+branch {b} ({t}) — {why}")
    elif reap["delegated"]:
        for t, b, why in reap["delegated"]:
            print(
                f"[reap] candidate worktree+branch {b} ({t}) — {why}; "
                "physical removal delegated to reclaim-worktrees.py + reap-branches.py acceptance ledgers"
            )
    elif reap["would"]:
        for t, b, why in reap["would"]:
            print(
                f"[reap] WOULD delegate worktree+branch {b} ({t}) — {why}  "
                "(run --apply to record the delegated candidate; removal still requires acceptance ledgers)"
            )
    if reap["kept"]:
        for t, why in reap["kept"]:
            print(f"[reap] kept {t}: {why}")

    if args.apply or args.breathe:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": int(now),
            "sessions": len(rows),
            "stalled": [r["sessionId"] for r in rows if r["state"] == "STALLED"],
            "alive": [r["sessionId"] for r in rows if r["state"] == "ALIVE"],
            "done": [r["sessionId"] for r in rows if r["state"] == "DONE"],
            "reaped": [b for _t, b, _w in reap["reaped"]],
            "delegated_reap": [b for _t, b, _w in reap["delegated"]],
        }
        with JOURNAL.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        RESIDUE_OUT.parent.mkdir(parents=True, exist_ok=True)
        RESIDUE_OUT.write_text(write_residue(rows))
        print(f"\n[apply] journal+residue written -> {JOURNAL.name}, {RESIDUE_OUT.name}")
        # hang each atom in the PERMANENT needs_human queue — the running system holds it, not a doc.
        h = hang_residue(rows)
        bits = []
        if h["created"]:
            bits.append(f"created {', '.join(h['created'])}")
        if h["refreshed"]:
            bits.append(f"refreshed {', '.join(h['refreshed'])}")
        if h["homed"]:
            bits.append(f"already-homed {len(h['homed'])}")
        if h.get("error"):
            bits.append(h["error"])
        print(f"[apply] permanent ledger ({Path(h['ledger']).name}): {'; '.join(bits) or 'no residue to hang'}")

    if args.breathe:
        breathe(rows, args.breathe, dry=args.dry_breathe)
    return 0


# worktrees we never reach into: the contended live checkout (shared with the daemon) and any
# tree currently hosting an ALIVE session (avoid colliding with moving work).
def _contended(cwd: str, alive_cwds: set[str]) -> bool:
    limen = str(ROOT).split("/.claude/worktrees/")[0]
    if cwd in (limen, str(ROOT)) or cwd in alive_cwds:
        return True  # live checkout / a moving session's tree
    if "/.claude/projects/" in cwd or not Path(cwd).is_dir():
        return True  # not a real, present worktree → don't reach in
    return False


def _breathe_counts() -> dict[str, int]:
    """Per-SID breathe history from this organ's own journal. Fail-open: unreadable → {}."""
    counts: dict[str, int] = {}
    for e in _read_jsonl(JOURNAL):
        sid = e.get("breathed")
        if isinstance(sid, str) and sid:
            counts[sid] = counts.get(sid, 0) + 1
    return counts


def escalate(rows: list[dict], counts: dict[str, int], dry: bool) -> None:
    """A session breathed >= N times that stalls AGAIN never receives the identical breath a third
    time — identical input, identical stall. It escalates to its OWN needs_human atom carrying the
    parked purpose and the exact resume command, so the census stays finish-not-park instead of an
    infinite re-breathe loop."""
    if not rows:
        return
    entries = []
    for r in rows:
        sid = r["sessionId"]
        n = counts.get(sid, 0)
        entries.append(
            {
                "tid": f"ASK-quicken-escalate-{sid[:8]}",
                "title": f"finish stalled session '{r['title'][:44]}' (breathed {n}x, still stalling)",
                "labels": ["quicken-residue", "quicken-escalate", "needs-human"],
                "context": (
                    f"Session {sid} ('{r['title'][:60]}') re-stalled after {n} guardrailed breathes — "
                    f"the identical continuation will not move it. Parked purpose (last prompt): "
                    f'"{r["last_prompt"][:120]}". Resume by hand or with a NEW instruction: '
                    f"claude --resume {sid}   (cwd {r['cwd']}). Auto-escalated by QUICKEN."
                ),
            }
        )
        print(f"  ESCALATE {sid[:8]} ({r['title'][:38]}) — breathed {n}x, hanging its own atom")
    if dry:
        print(f"  DRY would escalate {len(entries)} session(s); no atom hung, no journal write")
        return
    h = _hang_asks(entries)
    bits = [f"created {', '.join(h['created'])}" if h["created"] else "", h.get("error") or ""]
    print(f"  [escalate] {'; '.join(b for b in bits if b) or 'already homed'}")
    with JOURNAL.open("a") as fh:
        for r in rows:
            fh.write(
                json.dumps(
                    {
                        "ts": int(time.time()),
                        "escalated": r["sessionId"],
                        "title": r["title"][:60],
                        "breathes": counts.get(r["sessionId"], 0),
                    }
                )
                + "\n"
            )


def breathe(rows: list[dict], sel: str, dry: bool) -> None:
    import subprocess

    cap = positive_int_env("LIMEN_QUICKEN_BREATHE_CAP", 1)  # bounded-work contract: small
    to = positive_int_env("LIMEN_QUICKEN_BREATHE_TIMEOUT", 900)
    escalate_after = positive_int_env("LIMEN_QUICKEN_ESCALATE_AFTER", 2)
    # `all` breathes only STALLED (never auto-touch a moving session); a NAMED sid is an explicit
    # choice — honor it regardless of the flickery ALIVE/STALLED label (still skip contended trees).
    targets = [
        r for r in rows if not r["is_self"] and (r["sessionId"] == sel if sel != "all" else r["state"] == "STALLED")
    ]

    # contention = ANOTHER moving session shares the tree; a session never self-contends.
    def _others(sid):
        return {r["cwd"] for r in rows if r["state"] == "ALIVE" and r["sessionId"] != sid}

    targets = [r for r in targets if not _contended(r["cwd"], _others(r["sessionId"]))]
    # TERMINAL BLOCKED discipline: a session whose cascade landed on a reserved human lever
    # (decision.residue set => PROTOCOL layer) already has its ONE irreducible atom filed by
    # hang_residue(). Re-breathing it cannot help — the atom waits on a human, not on another breath —
    # and re-breathing a filed-blocked session IS the endless-loop failure the charter's
    # "BLOCKED once, then stop" rule forbids. Drop it from `all`-mode targets so it is filed once and
    # left silent; an explicitly NAMED sid still honors the operator's deliberate choice (debugging).
    if sel == "all":
        targets = [r for r in targets if not (r["decision"] and r["decision"].get("residue"))]
    targets.sort(key=lambda r: r["moved"])  # oldest-stalled first
    # a repeat offender (breathed >= N and stalled again) escalates instead of re-breathing —
    # only in `all` mode: an explicitly NAMED sid is a deliberate choice, honor it.
    counts = _breathe_counts()
    if sel == "all":
        repeat = [r for r in targets if counts.get(r["sessionId"], 0) >= escalate_after]
        targets = [r for r in targets if counts.get(r["sessionId"], 0) < escalate_after]
        escalate(repeat, counts, dry=dry)
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
            fh.write(
                json.dumps(
                    {"ts": int(time.time()), "breathed": r["sessionId"], "title": r["title"][:60], "ok": bool(ok)}
                )
                + "\n"
            )
        print(f"    -> {'finished' if ok else 'errored'} (journaled)")


if __name__ == "__main__":
    raise SystemExit(main())
