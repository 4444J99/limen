#!/usr/bin/env python3
"""converge-organ.py — make converge() AUTONOMIC. The last rung of the self-* ladder.

The engine (limen.converge) distills N divergent shots at one idea into the better version, but it
needs someone to FIND the divergent work and ACT on the result. This organ is that someone:

  ORACLE   — scan tasks.yaml for "multiverses": one idea (a task) that several lanes each produced a
             PR for (≥2 distinct PR URLs in its dispatch_log). Those PRs are divergent shots — exactly
             the "take many shots, then alchemically distill" telos (NOT janitorial dedup).
  DISTILL  — run converge() over each multiverse (offline dry-run kit by default — no network, always
             works; LIMEN_CONVERGE_LIVE=1 opts into the real AnthropicSynthesizer when available).
  WRITERS  — record the distillate + decision to logs/converge-log.jsonl (audit), and emit the
             gap-finder's next_shots as NEW bounded tasks (gaps become work) under the canonical
             queue lock. Reversible; never closes/merges PRs (that's the merge organ / his gate).

Gated OFF by default (LIMEN_CONVERGE=1). Bounded (LIMEN_CONVERGE_LIMIT, default 2 ideas/beat).
Read-mostly: the only tasks.yaml write is appending bounded gap-tasks, under the lock. Fail-open —
never crashes the heartbeat. ([[alchemical-convergence-method]], [[distillation-not-reduction]])
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
sys.path.insert(0, str(ROOT / "cli" / "src"))
PR_RE = re.compile(r"github\.com/[^/\s]+/[^/\s]+/pull/\d+")


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def find_multiverses(tasks: list[dict]) -> list[dict]:
    """An idea (task) is a MULTIVERSE when ≥2 lanes each produced a distinct PR for it — divergent
    shots worth distilling. Returns [{id, idea, shots:[{id,text,source}]}] newest-first by task."""
    out = []
    for t in tasks:
        seen: dict[str, dict] = {}
        for e in t.get("dispatch_log") or []:
            sid = str(e.get("session_id", ""))
            m = PR_RE.search(sid)
            if not m:
                continue
            url = m.group(0)
            if url in seen:
                continue
            agent = e.get("agent") or "?"
            seen[url] = {"id": f"{t.get('id')}:{agent}",
                         "text": str(e.get("output") or sid),
                         "source": f"{agent} {url}"}
        if len(seen) >= 2:  # ≥2 distinct PRs = a real multiverse
            out.append({"id": t.get("id"),
                        "idea": t.get("title") or t.get("id"),
                        "shots": list(seen.values())})
    return out


def _kit(live: bool):
    from limen.converge import _build_dry_run_kit  # offline, always available
    if not live:
        return _build_dry_run_kit()
    try:  # opt-in real synthesis; fall back to offline if anthropic/key missing
        from limen.converge import AnthropicSynthesizer, DeterministicScorer, LexicalGapFinder, \
            LexicalRanker, NoopPromoter
        return {"ranker": LexicalRanker(), "synthesizer": AnthropicSynthesizer(),
                "scorer": DeterministicScorer(), "promoter": NoopPromoter(),
                "gap_finder": LexicalGapFinder()}
    except Exception as exc:
        print(f"[converge] live kit unavailable ({exc}); using offline kit")
        return _build_dry_run_kit()


def _emit_gaps(gap_texts: list[str], origin_id: str, apply: bool) -> int:
    """Emit the gap-finder's next_shots as NEW bounded tasks through Tabularius tickets.

    Idempotent: a gap's id is derived from its text so the same gap never duplicates, including
    while it is pending in the keeper inbox.
    """
    if not gap_texts:
        return 0
    from limen.io import load_limen_file
    from limen.intake import contract_fields, github_pr_contract
    from limen.tabularius import pending_task_ids, submit_task_upsert
    tasks_path = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        lf = load_limen_file(tasks_path)
    except Exception as exc:
        print(f"[converge] could not load tasks for gap-emit ({exc}); skipping")
        return 0
    have = {t.id for t in lf.tasks} | pending_task_ids(tasks_path)
    added = 0
    session_id = os.environ.get("LIMEN_SESSION_ID", "converge-organ")
    for g in gap_texts:
        gid = "CONV-" + re.sub(r"[^a-z0-9]+", "-", g.lower())[:40].strip("-")
        if gid in have:
            continue
        task = dict(
            id=gid,
            title=g[:120],
            repo="organvm/limen",
            created=now.date(),
            status="open",
            target_agent="any",
            priority="low",
            type="converge-gap",
            context=f"gap surfaced by converge from {origin_id}",
            **contract_fields(github_pr_contract("organvm/limen", gid)),
        )
        if apply:
            submit_task_upsert(tasks_path, task, agent="converge-organ", session_id=session_id)
        have.add(gid)
        added += 1
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="converge organ — find multiverses, distill, emit gaps")
    ap.add_argument("--apply", action="store_true", help="write gap-tasks + the converge log")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_CONVERGE_LIMIT", "2")))
    ap.add_argument("--live", action="store_true", default=os.environ.get("LIMEN_CONVERGE_LIVE") == "1")
    args = ap.parse_args(argv)

    from limen.converge import Shot, converge

    data = _load_yaml(Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml")))
    multiverses = find_multiverses(data.get("tasks") or [])[: args.limit]
    if not multiverses:
        print("[converge] no multiverses (no idea has ≥2 divergent PRs yet) — nothing to distill")
        return 0

    kit = _kit(args.live)
    log_path = ROOT / "logs" / "converge-log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    total_gaps = 0
    for mv in multiverses:
        shots = [Shot(id=s["id"], text=s["text"], source=s["source"]) for s in mv["shots"]]
        try:
            r = converge(mv["idea"], shots, **kit)
        except Exception as exc:  # never crash the heartbeat
            print(f"[converge] {mv['id']}: cycle failed ({exc}); skipping")
            continue
        gaps = _emit_gaps(r.next_shots, mv["id"], args.apply) if args.apply else len(r.next_shots)
        total_gaps += gaps
        rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(), "idea_id": mv["id"],
               "idea": mv["idea"], "shots": len(shots), "score": round(r.score, 3),
               "promoted": r.promoted, "cited_losers": [s.id for s in r.cited_losers],
               "gaps_emitted": gaps}
        if args.apply:
            with log_path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        print(f"[converge] {mv['id']}: {len(shots)} shots → score {r.score:.2f} "
              f"promoted={r.promoted} losers={len(r.cited_losers)} gaps={gaps}")
    print(f"[converge] {len(multiverses)} multiverses distilled, {total_gaps} gaps "
          f"{'emitted' if args.apply else '(dry-run)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
