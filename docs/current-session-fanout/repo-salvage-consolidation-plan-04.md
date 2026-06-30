# Current Session Fanout Packet: Repo Salvage Consolidation

Generated: `2026-06-30`
Packet: `PLAN-04-1c17c8a3`
Task: `CSF-CAEB31D8-PLAN-04-1C17C8A3`
Theme: `repo-salvage-consolidation`
Owner repo: `organvm/limen`
Primary executor lane: `github_actions`
Status: `ready-for-executor-packets`

## Public-Safe Provenance

- Source session: `~/.codex/sessions/2026/06/30/rollout-2026-06-30T06-17-55-019f1809-13b4-7780-9b1f-d4584f872333.jsonl`
- Derivation scope: full session, not only the latest turn.
- Plan events read: `11`
- Unique plan sources: `10`
- Duplicate plan events: `1`
- Unconsolidated plan events: `0`
- Raw prompt and plan bodies are intentionally excluded from this packet.

| Source plan | Hash | Transcript line | Status |
|---|---|---:|---|
| Plan-Source Consolidation Proof And Fanout Repair | `7eb608baa99c` | `1450` | included |
| Consolidated Alpha-To-Omega Fleet Product System | `c93bc2c89ad8` | `1120` | included |
| Alpha-To-Omega Prompt Product Factory | `dbf49126308e` | `1046` | included |
| Full-Fleet Planner, Executor, And Contrib Mirror System | `3cc93e1d8fbd` | `1036` | included |
| Full-Fleet Planner, Executor, And Contrib Mirror System | `3cc93e1d8fbd` | `1026` | duplicate-included |
| Full-Fanout Current-Session Workstream Launcher | `0cb1773e8fef` | `965` | included |
| Current Session AND-Stack Intake | `1a3fd7bbca9d` | `931` | included |
| Unified Prompt-To-Revenue Operating System | `569ac3d1deea` | `893` | included |
| Dynamic Money-First Salvage Yard | `b0f5c26d40a3` | `883` | included |
| Whole-Machine Prompt-To-Product Salvage Yard | `f15665fb9ad3` | `873` | included |
| Full-Fleet Overnight Autonomy Fix | `21e790435885` | `6` | included |

## Planner Decision

Repo salvage is the inventory and consolidation layer between prompt history and product selection. It must produce owner packets from dynamic repo discovery, not from a fixed drive name or a hand-maintained repo list. It must also treat blocked local work as item-level state: a blocked repo, transfer, credential, drive, or deploy does not stop global product selection while another reversible repo/product packet exists.

The theme consumes these full-session requirements:

- dynamic storage and repo roots, with no stale named-drive blocker;
- whole-machine prompt/repo/product intake, with raw bodies kept private;
- repo-surface discovery across nested repos, duplicate remotes, worktrees, tests, deploys, docs, SEO, dirty state, and visibility state;
- consolidation graph assigning one canonical owner and one disposition per cluster;
- planner packets that emit executor criteria, not only prose plans;
- product selection that continues when one local work item is blocked;
- human gates for irreversible GitHub/org/App/credential/outbound actions.

## Owner Packets

| Packet | Owner Surface | Executor Criteria | Verification Predicate |
|---|---|---|---|
| `RS-01-repo-surface-inventory` | `scripts/repo-surface-ledger.py`, `docs/repo-surface-ledger.md` | Discover configured repo roots, nested repos, duplicate remotes, dirty state, default/upstream state, test/build surfaces, deploy/public proof surfaces, and private/public state. Emit redacted public summary plus private structured index. | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_substrate_repo_product_fanout.py -q` with nested repo and duplicate remote fixtures; then `python3 scripts/repo-surface-ledger.py --refresh --dry-run` or the repo's equivalent read-only mode. |
| `RS-02-salvage-consolidation-graph` | `scripts/salvage-yard-map.py`, `docs/current-session-fanout/repo-salvage-consolidation-plan-04.json` | Cluster repos, worktrees, prompts, product surfaces, duplicate apps, stale forks, and cache-only roots into canonical owner records. Each record gets one disposition: `build`, `verify`, `consolidate`, `private-sauce`, `publish-stage`, `blocked-human`, or `retire`. | Fixture with two repos sharing one remote/product surface must produce one canonical owner, one duplicate/superseded child, and no raw prompt text. |
| `RS-03-product-selection-bridge` | `scripts/product-ledger.py`, `docs/product-ledger.md` | Feed unblocked repo/product candidates into the global product ledger. If one repo is `blocked_local` or human-gated, keep selecting the next highest-value unblocked product. | Product-ledger fixture with one blocked product and one open revenue/product item must report global status `active` and return only unblocked next selections. |
| `RS-04-plan-source-proof` | `scripts/current-session-fanout.py`, `docs/current-session-fanout.md` | Every planner and executor packet for this theme must include the full unique `source_plan_hashes` set, plus duplicate accounting and `unconsolidated_plan_hashes == []`. | Synthetic session test must assert `plan_event_count`, `unique_plan_count`, duplicate marking, newest-to-oldest ordering, and full `source_plan_hashes` on planner and executor packets. |
| `RS-05-github-consolidation-gates` | `docs/consolidation/*`, `scripts/consolidation-gates.py` | Preserve current org-transfer/name-collision/App-token gates as blockers without running irreversible repo renames, transfers, credential writes, or App installs. | `PYTHONPATH=cli/src python3 scripts/consolidation-gates.py --write` must update only receipts and continue to show gated mutations as closed unless human approval is present. |
| `RS-06-outward-proof-staging` | `docs/positioning/*`, future repo-topic/README staging packet | For public-safe repos, stage proof mirrors: README/SEO positioning, GitHub topic/description recommendations, proof-page/case-study stubs, or explicit `not_applicable`. Do not publish, send, flip visibility, or mutate external identity surfaces. | Packet must contain an outward path or `not_applicable`, and the verification receipt must prove no outbound write command ran. |

## Executor Packet

`EXEC-GITHUB-ACTIONS-1C17C8A3` should take only reversible code and receipt work:

- implement or update the repo-surface ledger and salvage graph surfaces if absent;
- add focused tests for nested repos, duplicate remotes, duplicate product surfaces, blocked-local continuation, and source-plan hash propagation;
- emit public-safe docs and ignored/private structured indexes;
- leave irreversible consolidation actions staged as blockers.

Allowed files:

- `scripts/repo-surface-ledger.py`
- `scripts/salvage-yard-map.py`
- `scripts/product-ledger.py`
- `scripts/current-session-fanout.py`
- `scripts/consolidation-gates.py`
- `cli/tests/test_substrate_repo_product_fanout.py`
- `docs/repo-surface-ledger.md`
- `docs/product-ledger.md`
- `docs/current-session-fanout.md`
- `docs/current-session-fanout/repo-salvage-consolidation-plan-04.md`
- `docs/current-session-fanout/repo-salvage-consolidation-plan-04.json`
- `.limen-private/session-corpus/lifecycle/*.json`

Stop before:

- repo rename, repo transfer, owner rewrite `--apply`, App install, credential write, deploy, outbound send/post/comment, repo visibility flip, paid reset/top-up/overage, delete/wipe, mass merge, or live-root force-push;
- copying raw prompt or plan bodies into tracked files, task logs, PR bodies, commits, or outbound systems;
- treating one blocked repo or credential gate as a global product-selection stop.

## Blocked Local Work

| Blocker | Scope | Required Handling |
|---|---|---|
| This worktree lacks the newer `current-session-fanout.py`, `repo-surface-ledger.py`, `product-ledger.py`, and `salvage-yard-map.py` implementation seen in the live Limen checkout. | local branch | Record this packet and let executor lanes implement or port the surfaces deliberately; do not mutate the live root from this planner branch. |
| `logs/organ-health.json` and `logs/usage.json` are absent in this worktree snapshot. | local visibility | Use available board/docs receipts for this packet and require executors to regenerate health/usage receipts in their own lane before claiming live capacity state. |
| GitHub consolidation still has human-gated operations: collision renames, org transfers, App install/token wiring, and post-transfer owner rewrites. | external/irreversible | Keep read-only gate receipts current; wait for explicit human gate before mutation. |
| Cloudflare deploy auth and other credential gates remain in `docs/NEEDS-HUMAN-DIGEST.md`. | external credential | Record exact human action once; continue repo inventory, salvage graph, and product selection. |
| Codex reset, credit, top-up, or paid overage paths are owner-controlled. | spend gate | Mark lane `depleted` or `human-gated` if needed and route executor work to other reachable lanes. |

## Verification Predicates

Executor acceptance requires all applicable predicates to pass:

```bash
python3 -m py_compile scripts/repo-surface-ledger.py scripts/salvage-yard-map.py scripts/product-ledger.py scripts/current-session-fanout.py
PYTHONPATH=cli/src python3 -m pytest cli/tests/test_substrate_repo_product_fanout.py -q
python3 scripts/current-session-fanout.py --min-codex-planners 10 --executor-lanes auto --include-contrib --no-reset-spend --dry-run
python3 scripts/repo-surface-ledger.py --refresh --dry-run
python3 scripts/salvage-yard-map.py --dry-run
PYTHONPATH=cli/src python3 scripts/consolidation-gates.py --write
bash scripts/verify-whole.sh
```

This packet's own verification predicate is narrower because this branch is a planner worktree:

```bash
python3 - <<'PY'
from pathlib import Path
doc = Path("docs/current-session-fanout/repo-salvage-consolidation-plan-04.md").read_text()
required = [
    "7eb608baa99c", "c93bc2c89ad8", "dbf49126308e", "3cc93e1d8fbd",
    "0cb1773e8fef", "1a3fd7bbca9d", "569ac3d1deea", "b0f5c26d40a3",
    "f15665fb9ad3", "21e790435885", "EXEC-GITHUB-ACTIONS-1C17C8A3",
    "blocked_local", "global product selection",
]
missing = [item for item in required if item not in doc]
assert not missing, missing
forbidden = "<" + "proposed_plan>"
assert forbidden not in doc
assert "Raw prompt and plan bodies are intentionally excluded" in doc
PY
```
