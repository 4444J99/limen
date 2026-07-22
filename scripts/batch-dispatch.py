#!/usr/bin/env python3
"""batch-dispatch — seed tasks.yaml from audited Jules-ready issues."""

from __future__ import annotations

import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.intake import contract_fields, github_issue_contract
from limen.tabularius import pending_task_ids, submit_task_upsert

TASKS_YAML = Path(__file__).resolve().parent.parent / "tasks.yaml"

# 53 audited issues across 7 repos — compiled 2026-06-01
AUDIT = [
    # public-record-data-scrapper
    (
        "a-organvm/public-record-data-scrapper",
        236,
        "Frontend TS debt: ~357 errors + recharts dep drift",
        3,
    ),
    (
        "a-organvm/public-record-data-scrapper",
        238,
        "Propagate PR #234 completions to meta-organvm indices",
        2,
    ),
    (
        "a-organvm/public-record-data-scrapper",
        235,
        "Deploy prerequisites for PR #234 security hardening",
        2,
    ),
    (
        "a-organvm/public-record-data-scrapper",
        230,
        "IRF-APP-003: Phase 1 reliability hardening for ucc-mca-api",
        2,
    ),
    # peer-audited--behavioral-blockchain
    (
        "a-organvm/peer-audited--behavioral-blockchain",
        642,
        "Apply integrity ceiling compression to persisted score delta path",
        2,
    ),
    (
        "a-organvm/peer-audited--behavioral-blockchain",
        603,
        "fix: ERESOLVE dependency conflict + 42 npm audit vulns",
        1,
    ),
    (
        "a-organvm/peer-audited--behavioral-blockchain",
        592,
        "Fury consensus parameter contradicted three ways across corpus",
        1,
    ),
    (
        "a-organvm/peer-audited--behavioral-blockchain",
        591,
        "Triplicate research docs need dedup + provenance frontmatter",
        1,
    ),
    (
        "a-organvm/peer-audited--behavioral-blockchain",
        599,
        "Propagate brand identity from .env to platform-specific files",
        1,
    ),
    (
        "a-organvm/peer-audited--behavioral-blockchain",
        554,
        "Tests — billing flow + scope enforcement",
        2,
    ),
    (
        "a-organvm/peer-audited--behavioral-blockchain",
        551,
        "Tests — collision detection accuracy + performance",
        2,
    ),
    (
        "a-organvm/peer-audited--behavioral-blockchain",
        548,
        "Tests — access control + org isolation",
        2,
    ),
    # organvm-corpvs-testamentvm
    (
        "a-organvm/organvm-corpvs-testamentvm",
        375,
        "a-i--skills validate job red on main — 3 skills invalid frontmatter",
        1,
    ),
    (
        "a-organvm/organvm-corpvs-testamentvm",
        355,
        "IRF-SYS-185: VACUUM IRF missing from testamentvm",
        1,
    ),
    (
        "a-organvm/organvm-corpvs-testamentvm",
        352,
        "prompts distill default closeout requires missing clipboard-prompts precondition",
        1,
    ),
    (
        "a-organvm/organvm-corpvs-testamentvm",
        321,
        "IRF-SYS-110: governance doc structural error",
        1,
    ),
    (
        "a-organvm/organvm-corpvs-testamentvm",
        320,
        "IRF-SYS-109: Omega evidence map — zettelkasten #6 and #13",
        1,
    ),
    (
        "a-organvm/organvm-corpvs-testamentvm",
        350,
        "Backfill prompt index for 16 pre-existing session archives",
        2,
    ),
    (
        "a-organvm/organvm-corpvs-testamentvm",
        376,
        "Session receipt 2026-05-30 — post-restart hanging-task drain (DONE-569)",
        1,
    ),
    # petasum-super-petasum
    (
        "a-organvm/petasum-super-petasum",
        139,
        "Clean up ~100 stale bot branches (jules, sentinel, bolt, palette, copilot)",
        1,
    ),
    (
        "a-organvm/petasum-super-petasum",
        133,
        "Create prompt anti-pattern catalog (10+ anti-patterns)",
        1,
    ),
    (
        "a-organvm/petasum-super-petasum",
        126,
        "Create AI interaction manifest template",
        1,
    ),
    (
        "a-organvm/petasum-super-petasum",
        124,
        "Create prompt template library (5+ versioned skeletons)",
        1,
    ),
    (
        "a-organvm/petasum-super-petasum",
        132,
        "Define AI-free practice cadence for cognitive atrophy prevention",
        1,
    ),
    (
        "a-organvm/petasum-super-petasum",
        127,
        "Document provider policy tracking (OpenAI, Anthropic, Google, etc.)",
        1,
    ),
    (
        "a-organvm/petasum-super-petasum",
        122,
        "Create pseudonymization and redaction guidelines",
        1,
    ),
    (
        "a-organvm/petasum-super-petasum",
        131,
        "Address platform memory lock-in (ChatGPT/Claude memory risks)",
        2,
    ),
    (
        "a-organvm/petasum-super-petasum",
        136,
        "Add safety constraints for non-interactive agent modes",
        2,
    ),
    # organvm-engine
    (
        "a-organvm/organvm-engine",
        84,
        "Add seed.yaml validation for missing produces/consumes edges",
        1,
    ),
    (
        "a-organvm/organvm-engine",
        83,
        "Add --format json flag to organvm registry list command",
        1,
    ),
    (
        "a-organvm/organvm-engine",
        71,
        "fix(irf): stats command undercounts newly added tail items",
        1,
    ),
    (
        "a-organvm/organvm-engine",
        64,
        "descent: content-based detection for CodeQL and release automation",
        2,
    ),
    (
        "a-organvm/organvm-engine",
        60,
        "descent: add type-checking to 6 remaining repos",
        2,
    ),
    (
        "a-organvm/organvm-engine",
        61,
        "descent: expand branch protection to all organs (~45 repos)",
        2,
    ),
    (
        "a-organvm/organvm-engine",
        70,
        "fix(session): hanging review and plans commands in large repos",
        2,
    ),
    (
        "a-organvm/organvm-engine",
        76,
        "feat: SOP staleness detection cross-reference SOPs against governed code",
        2,
    ),
    (
        "a-organvm/organvm-engine",
        74,
        "feat: handoff staleness detection and workspace-wide handoff listing",
        2,
    ),
    (
        "a-organvm/organvm-engine",
        73,
        "feat: context sync diff/changelog between runs",
        2,
    ),
    # conversation-corpus-engine
    (
        "organvm-i-theoria/conversation-corpus-engine",
        17,
        "IRF-CCE-029/037: Testament vacuum — S38-S41 sessions lack testament files",
        1,
    ),
    (
        "organvm-i-theoria/conversation-corpus-engine",
        19,
        "IRF-CCE-032: Omega evidence format specimen missing from GH#14 handoff",
        1,
    ),
    (
        "organvm-i-theoria/conversation-corpus-engine",
        18,
        "IRF-CCE-031: CCE lacks inquiry-log.yaml for research activities",
        1,
    ),
    (
        "organvm-i-theoria/conversation-corpus-engine",
        23,
        "IRF-CCE-038: Cross-repo commercial awareness gap (CCE ↔ pipeline)",
        1,
    ),
    (
        "organvm-i-theoria/conversation-corpus-engine",
        22,
        "IRF-CCE-036: seed.yaml planned produces edges for 3 ORGAN-III vehicles",
        1,
    ),
    (
        "organvm-i-theoria/conversation-corpus-engine",
        21,
        "IRF-CCE-035: Omega evidence map — note commercial spec for criteria #9/#10",
        1,
    ),
    (
        "organvm-i-theoria/conversation-corpus-engine",
        25,
        "CPU throttling fix — Layer 4 orchestration tuning pending",
        1,
    ),
    (
        "organvm-i-theoria/conversation-corpus-engine",
        27,
        "feat: build corpus persona-extract subcommand",
        2,
    ),
    (
        "organvm-i-theoria/conversation-corpus-engine",
        24,
        "IRF-CCE-039: Derive implementation plan from commercial architecture spec",
        2,
    ),
]


def next_id(tasks, pending_ids=None):
    ids = [t.get("id", "") for t in tasks]
    ids.extend(pending_ids or [])
    nums = []
    for i in ids:
        parts = i.replace("LIMEN-", "").split("-")
        try:
            nums.append(int(parts[0]))
        except (ValueError, IndexError):
            pass
    return f"LIMEN-{max(nums) + 1:03d}" if nums else "LIMEN-015"


def main():
    with open(TASKS_YAML) as f:
        data = yaml.safe_load(f)

    tasks = data.setdefault("tasks", [])
    pending_ids = pending_task_ids(TASKS_YAML)
    nid = next_id(tasks, pending_ids)
    base_num = int(nid.replace("LIMEN-", ""))
    added = 0
    session_id = "batch-dispatch"

    for repo, num, title, cost in AUDIT:
        # skip if already tracked by issue number
        url = f"https://github.com/{repo}/issues/{num}"
        if any(url in str(t.get("urls", [])) for t in tasks):
            continue

        tid = f"LIMEN-{base_num + added:03d}"
        if tid in pending_ids:
            continue
        task = dict(
            id=tid,
            title=title,
            repo=repo,
            type="code",
            target_agent="jules",
            priority="high" if cost >= 3 else "medium",
            budget_cost=cost,
            status="dispatched",
            origin="obligation",
            horizon="present",
            value_case=f"Close audited GitHub issue {repo}#{num}",
            urls=[url],
            context=f"Audited 2026-06-01 from Jules-ready batch. Fix issue #{num} in {repo}.",
            labels=["batch-2026-06-01"],
            created="2026-06-01",
            dispatch_log=[],
            **contract_fields(github_issue_contract(repo, num)),
        )
        submit_task_upsert(TASKS_YAML, task, agent="batch-dispatch", session_id=session_id)
        pending_ids.add(tid)
        added += 1

    print(f"Submitted {added} task upsert ticket(s). Total after keeper fold: {len(tasks) + added}")


if __name__ == "__main__":
    main()
