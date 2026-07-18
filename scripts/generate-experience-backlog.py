#!/usr/bin/env python3
"""generate-experience-backlog — convert the experience audit's gap list into bounded fleet tasks.

experience-audit.py scores every derived public surface against its visitor-experience budget (the
mechanical X1..X7 rungs) and the experience-judge skill appends VISUAL verdicts to the judgment
register. What remains — surfaces over budget, surfaces a visual judgment failed — is PER-SURFACE
work, and that ships as tasks.yaml tasks the fleet consumes (the generate-seo-backlog pattern), never
as one mega-session.

Reads logs/experience-audit.json (the sweep artifact) + institutio/observatory/experience-judgments.yaml
(visual verdicts) + value-repos.json (priority). Emits, bounded:
  EXP-<surface>-budget-<mmdd>   a surface over its mechanical budget — context embeds the failed rungs
                                and the literal done-predicate (experience-audit.py --surface X --check
                                exits 0 after the fix ships and the beat re-sweeps).
  EXP-<surface>-visual-<mmdd>   a surface whose latest visual judgment is verdict: fail — context
                                embeds the defects and the suggested fix, citing the screenshot sha.

Read-only by default; --apply only when LIMEN_EXPERIENCE_BACKLOG_APPLY=1 (the beat's armed valve).
Floor-gated + deduped + capped, mirroring the seo-backlog template constants.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.intake import contract_fields, github_pr_contract  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import submit_task_upsert  # noqa: E402

# Artifacts + registries resolve from the SCRIPT'S OWN TREE (the gitvs ROOT convention); only the task
# board stays env-resolved (LIMEN_TASKS/cwd), since the beat feeds the live board from wherever it runs.
ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "logs" / "experience-audit.json"
JUDGMENTS = ROOT / "institutio" / "observatory" / "experience-judgments.yaml"

_EXP_LABELS = {"experience", "product"}
_ACTIVE = {"open", "dispatched", "in_progress", "needs_human", "failed_blocked"}
_LEVER_KEYS = {"exp-budget", "exp-visual"}


def _audit() -> dict:
    try:
        return json.loads(AUDIT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _value_rank() -> dict[str, int]:
    try:
        repos = json.loads((ROOT / "value-repos.json").read_text()).get("repos") or []
        return {r: i for i, r in enumerate(repos)}
    except Exception:
        return {}


def _judgments() -> dict[str, dict]:
    """Latest visual verdict per surface id (newest row wins)."""
    try:
        reg = yaml.safe_load(JUDGMENTS.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for sid, rows in (reg.get("judgments") or {}).items():
        row_list = rows if isinstance(rows, list) else [rows]
        if not row_list:
            continue
        latest = row_list[-1]
        if isinstance(latest, dict):
            out[sid] = latest
    return out


def _repo_for(entry: dict) -> str | None:
    """A surface entry carries no repo; derive the owning repo from the value-repo rank by matching
    the surface url's host/path against a repo slug. When no repo is derivable the task targets the
    corpus repo (the surface registry's owner) so the contract still has a durable receipt owner."""
    return None


def _plan(tasks: list[Task], floor: int, max_new: int) -> tuple[list[Task], dict]:
    audit = _audit()
    surfaces = audit.get("surfaces") or {}
    if not surfaces:
        return [], {"no_audit": True}
    open_exp = sum(1 for t in tasks if t.status == "open" and (set(t.labels or []) & _EXP_LABELS))
    info = {"open_exp": open_exp, "floor": floor, "audited": audit.get("audited")}
    if open_exp >= floor:
        return [], info
    need = min(floor - open_exp, max_new)

    rank = _value_rank()
    judgments = _judgments()
    existing = {t.id for t in tasks}
    active_pairs = {
        (t.repo or t.title, t.labels[0])
        for t in tasks
        if t.labels and t.labels[0] in _LEVER_KEYS and t.status in (_ACTIVE | {"done", "archived"})
    }

    # Order by value rank of any repo the surface url mentions, else neutral. Surfaces sort stably by id
    # so the plan is deterministic (correct-when-empty: no rank -> pure id order).
    def _rank_for(sid: str, entry: dict) -> int:
        url = str(entry.get("url") or "").lower()
        best = 999
        for repo, r in rank.items():
            slug = repo.split("/")[-1].lower()
            if slug and slug in url:
                best = min(best, r)
        return best

    # work items: over-budget mechanical failures first, then failed visual judgments.
    items: list[tuple[str, str, dict]] = []
    for sid, entry in sorted(surfaces.items(), key=lambda kv: (_rank_for(kv[0], kv[1]), kv[0])):
        if not entry.get("pass"):
            items.append(("exp-budget", sid, entry))
    for sid, entry in sorted(surfaces.items(), key=lambda kv: (_rank_for(kv[0], kv[1]), kv[0])):
        j = judgments.get(sid)
        if j and j.get("verdict") == "fail":
            items.append(("exp-visual", sid, entry))

    stamp = date.today().isoformat()
    mmdd = date.today().strftime("%m%d")
    new: list[Task] = []
    for key, sid, entry in items:
        if len(new) >= need:
            break
        if (sid, key) in active_pairs:
            continue
        tid = f"EXP-{sid}-{key.split('-', 1)[1]}-{mmdd}"
        if tid in existing:
            continue
        existing.add(tid)
        active_pairs.add((sid, key))
        prio = "high" if _rank_for(sid, entry) < 999 else "medium"
        # The receipt owner is the corpus repo (the surface registry's home); the done-predicate is
        # the per-surface check re-run after the fix ships and the beat re-sweeps.
        receipt_repo = "organvm/organvm-corpvs-testamentvm"
        if key == "exp-budget":
            rungs = entry.get("rungs") or {}
            misses = sorted(k for k, v in rungs.items() if v is False)
            title = f"Bring surface '{sid}' back within its visitor-experience budget"
            ctx = (
                f"The public surface '{sid}' ({entry.get('url')}) fails rungs {', '.join(misses) or '(unknown)'} "
                "of the visitor-experience standard (X1 reachable 200 · X2 ttfb <= budget · X3 transfer "
                "<= budget · X4 requests <= budget · X5 no broken images · X6 no console errors · X7 "
                f"non-empty title). Measured: status={entry.get('status')} ttfb={entry.get('ttfb_ms')}ms "
                f"transfer={entry.get('transfer_kb')}kb requests={entry.get('requests')} "
                f"broken_images={entry.get('broken_images')} console_errors={entry.get('console_errors')}. "
                f"Largest asset: {entry.get('largest_asset')}. Fix the deployed surface at its source "
                "(the repo that publishes this URL), re-deploy, and let the beat re-sweep. Done ⟺ "
                f"`python3 scripts/experience-audit.py --surface {sid} --check` exits 0 on the next sweep."
            )
        else:
            j = judgments.get(sid) or {}
            defects = j.get("defects") or []
            title = f"Address the failed visual judgment for surface '{sid}'"
            ctx = (
                f"The public surface '{sid}' ({entry.get('url')}) failed its latest VISUAL judgment "
                f"(scores {j.get('scores')}, screenshot sha256 {j.get('screenshot_sha256')}). Defects: "
                f"{'; '.join(str(d) for d in defects) or '(see the judgment register)'}. Suggested fix: "
                f"{j.get('suggested_fix') or '(none recorded)'}. Fix the layout/typography/coherence/trust "
                "issue at the surface's source and re-deploy, then re-run the experience-judge skill to "
                "record a passing verdict. Done ⟺ the newest row for this surface in "
                "institutio/observatory/experience-judgments.yaml is verdict: pass."
            )
        new.append(
            Task(
                id=tid,
                title=title,
                repo=receipt_repo,
                type="code",
                target_agent="any",
                priority=prio,
                budget_cost=1,
                status="open",
                labels=[key, "experience", "product", "generated"],
                urls=[],
                context=ctx + f" [experience-backlog {stamp}]",
                **contract_fields(github_pr_contract(receipt_repo, tid)),
                depends_on=[],
                created=stamp,
                dispatch_log=[],
            )
        )
    return new, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--floor", type=int, default=int(os.environ.get("LIMEN_EXPERIENCE_FLOOR", "6")))
    ap.add_argument("--max-new", type=int, default=int(os.environ.get("LIMEN_EXPERIENCE_MAX", "6")))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    apply = args.apply and os.environ.get("LIMEN_EXPERIENCE_BACKLOG_APPLY") == "1"

    path = Path(args.tasks)
    lf = load_limen_file(path)
    new, info = _plan(lf.tasks, args.floor, args.max_new)

    if info.get("no_audit"):
        print(
            "# generate-experience-backlog: no sweep artifact (run experience-audit.py --sweep first) — nothing to generate."
        )
        return 0
    print(f"# generate-experience-backlog: open-exp={info['open_exp']} floor={info['floor']} audited={info['audited']}")
    if not new:
        print("experience queue healthy or every (surface,lever) active — nothing to generate.")
        return 0
    print(f"-> generating {len(new)} experience tasks (cap {args.max_new})")
    for t in new:
        print(f"| {t.id} | {t.repo} | {t.priority} | {t.labels[0]} |")
    if not apply:
        if args.apply:
            print("\n--apply passed but LIMEN_EXPERIENCE_BACKLOG_APPLY != 1 — armed valve closed; nothing applied.")
        else:
            print(f"\ndry-run — re-run with --apply (and LIMEN_EXPERIENCE_BACKLOG_APPLY=1) to append {len(new)} tasks.")
        return 0
    fresh = load_limen_file(path)
    have = {t.id for t in fresh.tasks}
    to_add = [t for t in new if t.id not in have]
    if not to_add:
        print("\n(all planned tasks already present after fresh re-read — nothing applied.)")
        return 0
    if os.environ.get("LIMEN_TICKETS_PRODUCE") == "1":
        session_id = os.environ.get("LIMEN_SESSION_ID", "generate-experience-backlog")
        for t in to_add:
            submit_task_upsert(path, t, agent="generate-experience-backlog", session_id=session_id)
        print(f"\nsubmitted {len(to_add)} experience upsert tickets to the keeper's inbox.")
        return 0
    fresh.tasks.extend(to_add)
    save_limen_file(path, fresh)
    print(f"\napplied: appended {len(to_add)} experience tasks -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
