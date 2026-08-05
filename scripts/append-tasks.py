import sys
import yaml
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.intake import contract_fields, github_issue_contract, github_pr_contract
from limen.tabularius import pending_task_ids, submit_task_upsert

tasks_to_add = [
    {"id": "LIMEN-060", "title": "feat: implement MCP tool wrappers for all 5 organvm CLIs", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/89"]},
    {"id": "LIMEN-061", "title": "Add seed.yaml validation for missing produces/consumes edges", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/84"]},
    {"id": "LIMEN-062", "title": "Add --format json flag to organvm registry list command", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/83"]},
    {"id": "LIMEN-063", "title": "feat: corpus knowledge graph module (organvm corpus)", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/81"]},
    {"id": "LIMEN-064", "title": "feat: SOP staleness detection — cross-reference SOPs against governed code", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/76"]},
    {"id": "LIMEN-065", "title": "feat: exit interview testimony for documentation-only repos", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/75"]},
    {"id": "LIMEN-066", "title": "feat: handoff staleness detection and workspace-wide handoff listing", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/74"]},
    {"id": "LIMEN-067", "title": "feat: context sync diff/changelog between runs", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/73"]},
    {"id": "LIMEN-068", "title": "fix(irf): stats command undercounts newly added tail items", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/71"]},
    {"id": "LIMEN-069", "title": "fix(session): investigate hanging review and plans commands in large repos", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/70"]},
    {"id": "LIMEN-070", "title": "network: R3 kinship mirror research — community identification", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/66"]},
    {"id": "LIMEN-071", "title": "descent: content-based detection for CodeQL and release automation", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/64"]},
    {"id": "LIMEN-072", "title": "descent: expand branch protection to all organs", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/61"]},
    {"id": "LIMEN-073", "title": "descent: add type-checking to 6 remaining repos", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/60"]},
    {"id": "LIMEN-074", "title": "feat: Ring 4 — external chain anchoring (Base L2 / Celestia)", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/55"]},
    {"id": "LIMEN-075", "title": "feat: Stakeholder Portal /testament/ route", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/54"]},
    {"id": "LIMEN-076", "title": "feat: testament sonic bridge — OSC to alchemical-synthesizer", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/49"]},
    {"id": "LIMEN-077", "title": "Fix soak-test LaunchAgent — gh CLI auth fails under launchd", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/41"]},
    {"id": "LIMEN-078", "title": "feat: formalize Score→Rehearse→Perform ritual in Conductor lifecycle", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/10"]},
    {"id": "LIMEN-079", "title": "Fix npm audit vulnerabilities (drizzle-orm, next) in stakeholder-portal", "repo": "a-organvm/stakeholder-portal", "urls": ["https://github.com/a-organvm/stakeholder-portal/issues/49"]},
    {"id": "LIMEN-080", "title": "Refresh stale CLAUDE.md autogen tail (2026-03-08)", "repo": "a-organvm/universal-mail--automation", "urls": ["https://github.com/a-organvm/universal-mail--automation/issues/3"]},
    {"id": "LIMEN-081", "title": "[IRF-RES-003] Define 'readiness' construct independently of operationalization", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/343"]},
    {"id": "LIMEN-082", "title": "[IRF-RES-013] Temporal staging refactor (validate previous-with-current)", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/342"]},
    {"id": "LIMEN-083", "title": "[IRF-RES-011] Hybrid topology law codification (effective vs nominal coupling)", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/341"]},
    {"id": "LIMEN-084", "title": "[IRF-RES-004] Bayesian factor analysis on omega scorecard", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/340"]},
    {"id": "LIMEN-085", "title": "[IRF-RES-006] Controlled vocabulary registry (retroactive reconciliation)", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/339"]},
    {"id": "LIMEN-086", "title": "Secret Scanning Alert triage: 6862 potential leaks", "repo": "organvm-i-theoria/.github", "urls": ["https://github.com/organvm-i-theoria/.github/issues/441"]},
    {"id": "LIMEN-087", "title": "IRF-CCE-027: Post Office discover uses wrong API (gizmos != Projects)", "repo": "organvm-i-theoria/conversation-corpus-engine", "urls": ["https://github.com/organvm-i-theoria/conversation-corpus-engine/issues/16"]},
    {"id": "LIMEN-088", "title": "Monthly Organ Audit — 2026-06-01 manual triage", "repo": "a-organvm/orchestration-start-here", "urls": ["https://github.com/a-organvm/orchestration-start-here/issues/165"]},
    {"id": "LIMEN-089", "title": "Fix a-i--skills validate job red on main — 3 skills invalid frontmatter", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/375"]},
    {"id": "LIMEN-090", "title": "Fix prompts distill input file missing: clipboard-prompts.json", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/352"]},
    {"id": "LIMEN-091", "title": "PR #234 security gate prerequisites (JWT_SECRET, org_id)", "repo": "a-organvm/public-record-data-scrapper", "urls": ["https://github.com/a-organvm/public-record-data-scrapper/issues/235"]},
    {"id": "LIMEN-092", "title": "Dedup triplicate research docs in docs/architecture/", "repo": "a-organvm/peer-audited--behavioral-blockchain", "urls": ["https://github.com/a-organvm/peer-audited--behavioral-blockchain/issues/591"]},
    {"id": "LIMEN-093", "title": "Restore missing INST-INDEX-RERUM-FACIENDARUM.md", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/355"]},
    {"id": "LIMEN-094", "title": "Audit 26 missing READMEs across 148 repos", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/387"]},
    {"id": "LIMEN-095", "title": "Session receipt 2026-05-30 — post-restart hanging-task drain", "repo": "a-organvm/organvm-corpvs-testamentvm", "urls": ["https://github.com/a-organvm/organvm-corpvs-testamentvm/issues/376"]},
    {"id": "LIMEN-096", "title": "Submit conference talk proposals — AI-Conductor path", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/42"]},
    {"id": "LIMEN-097", "title": "Promotion Recommendations — June 2026 triage", "repo": "a-organvm/orchestration-start-here", "urls": ["https://github.com/a-organvm/orchestration-start-here/issues/166"]},
    {"id": "LIMEN-098", "title": "Staggered Walkthrough Schedule triage", "repo": "organvm-i-theoria/.github", "urls": ["https://github.com/organvm-i-theoria/.github/issues/442"]},
    {"id": "LIMEN-099", "title": "network: R3 kinship mirror research — community identification", "repo": "a-organvm/organvm-engine", "urls": ["https://github.com/a-organvm/organvm-engine/issues/66"]}, # Wait, this is a dupe of 70.
    {"id": "LIMEN-100", "title": "Integrity ceiling Follow-up: contracts.service.ts delta path", "repo": "a-organvm/peer-audited--behavioral-blockchain", "urls": ["https://github.com/a-organvm/peer-audited--behavioral-blockchain/issues/642"]}, # Wait, 018 was this too.
]

# Correcting dupes for 99 and 100
tasks_to_add[39] = {"id": "LIMEN-099", "title": "IRF-CCE-033: Execute CCE commercial architecture — H1 actions", "repo": "organvm-i-theoria/conversation-corpus-engine", "urls": ["https://github.com/organvm-i-theoria/conversation-corpus-engine/issues/20"]}
tasks_to_add[40] = {"id": "LIMEN-100", "title": "Audit all GitHub orgs for open issues suitable for Jules dispatch (Batch 3)", "repo": "a-organvm/orchestration-start-here", "urls": []}

tasks_path = Path('tasks.yaml').expanduser()
if not tasks_path.exists():
    tasks_path = Path('~/Workspace/limen/tasks.yaml').expanduser()

with open(tasks_path) as f:
    data = yaml.safe_load(f)

existing_ids = {t['id'] for t in data['tasks']} | pending_task_ids(tasks_path)
added_count = 0
session_id = "append-tasks"
for t in tasks_to_add:
    if t['id'] not in existing_ids:
        new_task = {
            "id": t['id'],
            "title": t['title'],
            "repo": t['repo'],
            "type": "code" if "feat" in t['title'] or "fix" in t['title'] else "docs",
            "target_agent": "jules",
            "priority": "medium",
            "budget_cost": 2 if "feat" in t['title'] else 1,
            "status": "dispatched",
            "origin": "obligation",
            "horizon": "present",
            "value_case": f"Close the audited source obligation {t['id']} in {t['repo']}",
            "labels": ["batch-2026-06-01"],
            "urls": t['urls'],
            "context": f"Audited 2026-06-01 from Jules-ready batch. {t['title']}",
            "created": date.today().isoformat(),
            "dispatch_log": []
        }
        if t["urls"]:
            issue_number = t["urls"][0].rsplit("/", 1)[-1]
            new_task.update(contract_fields(github_issue_contract(t["repo"], issue_number)))
        else:
            new_task.update(contract_fields(github_pr_contract(t["repo"], t["id"])))
        submit_task_upsert(tasks_path, new_task, agent="append-tasks", session_id=session_id)
        existing_ids.add(t["id"])
        added_count += 1

print(f"Submitted {added_count} task upsert ticket(s). Total after keeper fold: {len(data['tasks']) + added_count}")
