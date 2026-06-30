# PLAN-06 contrib-mirror owner packets

Generated: `2026-06-30`
Task: `CSF-CAEB31D8-PLAN-06-0BD58D68`
Packet: `PLAN-06-0bd58d68`
Theme: `contrib-mirror`
Repository: `organvm/limen`

This is a public-safe planner receipt. It contains hashes, owner scopes,
criteria, predicates, and blocker receipts only. Do not paste raw source prompt
or plan bodies into this file, task logs, commits, pull requests, or outbound
systems.

## Source proof

- Source session: `~/.codex/sessions/2026/06/30/rollout-2026-06-30T06-17-55-019f1809-13b4-7780-9b1f-d4584f872333.jsonl`
- Session hash: `caeb31d884ab514a4cb1d2a2`
- Session events read: `1452`
- User messages read: `44`
- Prompt bytes read: `78216`
- Prompt hashes found: `44` total, `19` unique
- Plan events found: `11` total, `10` unique, `1` duplicate
- Unique source plan hashes: `7eb608baa99c`, `c93bc2c89ad8`,
  `dbf49126308e`, `3cc93e1d8fbd`, `0cb1773e8fef`, `1a3fd7bbca9d`,
  `569ac3d1deea`, `b0f5c26d40a3`, `f15665fb9ad3`, `21e790435885`
- Source prompt hash sample: `4c72667b4d9a1d74b666b8e5`,
  `f970b04af2b06193fcaf9ca4`, `5cd8d801fb9ec350968507ad`,
  `51b4520a624f45dc78be0d98`, `e27388c5c8a724b1070d4aaf`,
  `5470f2595dfe3afd1fd6e53b`

The packet was derived from the full session scan above, not from the latest
turn alone.

## Planner decision

`contrib-mirror` is not a request to auto-comment on upstream projects. It is a
bounded mirror/ledger stream for the open-source contribution system: preserve
the current contribution hub as the state surface, reconcile the two existing
engines, then expose contribution outcomes as product/reputation proof.

Outbound actions remain human-gated: GitHub comments, PR creation, issue
creation, public posting, credential changes, and org/repo visibility changes
must be staged for approval.

## Owner packets

### PLAN06-OWNER-01 contrib hub ledger

- Owner repo/worktree: `organvm/contrib` at
  `/Users/4jp/Workspace/organvm/contrib`
- Current local state: clean checkout, `main...origin/main [behind 3]`
- Executor fit: `codex` to reconcile, then `opencode` only for narrow
  doc/script edits
- Executor criteria:
  - Treat `LEDGER.yaml` and `LEDGER.md` as derived state.
  - Fix stale identity/state in `seed.yaml` roots or `ledger-overrides.yaml`,
    then regenerate; do not hand-edit the generated table.
  - Keep protocol-due outbound actions as queued receipts, not posted comments.
  - Record the missing seed-root state before attempting a live GitHub refresh.
- Verification predicate:
  - `python3 scripts/refresh-ledger.py --offline --check`
  - If the seed root is restored and GitHub auth is intentionally available:
    `python3 scripts/refresh-ledger.py --check`
  - `git diff --check`
- Expected receipt:
  - Updated `LEDGER.yaml`/`LEDGER.md` only through `scripts/refresh-ledger.py`,
    plus a short note in `ROADMAP.md` if a Phase 1 item changes status.
- Stop condition:
  - Stop before posting bumps, closing PRs, deleting tracking workspaces, or
    changing public repository visibility.

### PLAN06-OWNER-02 engine-A ledger backend

- Owner repo/worktree: `a-organvm/organvm-engine` at
  `/Users/4jp/Workspace/a-organvm/organvm-engine`
- Current local state: branch `limen/limen-060-4a78`; contrib package and
  `tests/test_contrib.py` present
- Executor fit: `codex` for interface design; `opencode` or `jules` for a
  focused implementation once the hub ledger contract is explicit
- Executor criteria:
  - Add or verify a ledger-backed discovery path for
    `organvm_engine.contrib`.
  - Preserve the current `seed.yaml` discovery and PR-status behavior unless a
    test proves the replacement covers it.
  - Backflow classification must read contribution state from the hub ledger
    when available, while retaining local test fixtures for hermetic tests.
- Verification predicate:
  - `python3 -m pytest -q tests/test_contrib.py`
  - `python3 -m py_compile src/organvm_engine/contrib/*.py src/organvm_engine/cli/contrib.py`
- Expected receipt:
  - Changed engine files, changed tests, and a note naming whether the hub
    ledger is read-only, write-capable, or still blocked by owner packet 01.
- Stop condition:
  - Stop before moving the legacy engine, changing public CLI semantics, or
    writing corpus/backflow outputs outside the owner packet.

### PLAN06-OWNER-03 engine-B parity map

- Owner repo/worktree: `a-organvm/orchestration-start-here` at
  `/Users/4jp/Workspace/a-organvm/orchestration-start-here`
- Current local state: clean tracked files, `main...origin/main [behind 9]`,
  untracked `open_issues.json`
- Executor fit: `codex` for the parity map; `opencode` for narrow code changes
  after packet 02 defines the shared ledger contract
- Executor criteria:
  - Map `contrib_engine` scanner, campaign, GitHub client, fieldwork, and
    monitor surfaces to the hub ledger fields.
  - Do not run outreach or mutate GitHub; this packet only preserves parity and
    makes the future merge testable.
  - Classify `open_issues.json` as local/generated/intake residue before
    staging or deleting it.
- Verification predicate:
  - `python3 -m pytest -q tests/test_contrib_scanner.py tests/test_contrib_github_client.py tests/test_contrib_orchestrator.py tests/test_contrib_monitor.py`
  - `python3 -m py_compile contrib_engine/*.py`
- Expected receipt:
  - A parity table or adapter test showing which Engine B fields map to the hub
    ledger and which still need an owner decision.
- Stop condition:
  - Stop before deleting `open_issues.json`, sending outreach, merging engines,
    or changing campaign persistence formats.

### PLAN06-OWNER-04 public proof mirror

- Owner repo/worktree: `organvm/limen` plus the current public-surface owner
  selected by the executor
- Current local state: no public contribution mirror is launched from this
  packet
- Executor fit: `codex` to select the owner surface; `jules` or
  `github_actions` only after a concrete repo, branch, and predicate exist
- Executor criteria:
  - Consume hub-ledger outputs only; do not scrape private archaeology or raw
    prompt/session files.
  - Render contribution outcomes as proof categories: merged, open, no-PR,
    closed, protocol-due, and post-close.
  - Redact or omit private notes and local paths before any public surface.
  - Keep this downstream of owner packet 01; if the hub ledger is stale, surface
    the stale receipt and continue product selection elsewhere.
- Verification predicate:
  - `python3 scripts/generate-positioning.py --check` when the selected owner
    is Limen positioning.
  - The selected owner repo must also define its own build/test predicate before
    executor dispatch.
- Expected receipt:
  - A concrete owner repo/path, generated surface path, redaction proof, and
    build/check command.
- Stop condition:
  - Stop before publishing, deploying, or flipping repository visibility.

## Blocked local work

- `logs/organ-health.json` and `logs/usage.json` are absent in this worktree, so
  this planner could not use those runtime health/runway receipts.
- `organvm/contrib` ledger verification currently blocks locally:
  `python3 scripts/refresh-ledger.py --offline --check` reports missing seed
  root `/Users/4jp/Code/upstream/community` and stale derived ledger output.
- `a-organvm/orchestration-start-here` has untracked `open_issues.json`; do not
  classify it as source until owner packet 03 inspects it.
- These are owner-packet blockers, not global product-selection blockers.
  Continue the current-session fanout through the other planner and executor
  streams while the contrib owners are reconciled.

## Dispatch gate

An executor packet is dispatchable only when it names:

- owner repo/worktree;
- allowed file scope;
- exact verification predicate;
- expected receipt path;
- no raw prompt/plan body exposure;
- no outbound or irreversible action without a fresh human gate.

For this packet, the first safe executor is owner packet 01 in read-only/offline
mode. Owner packets 02 and 03 are ready for design/test work after packet 01
records whether the hub ledger contract is current or stale. Owner packet 04
stays a downstream selection packet until a concrete public surface owner is
named.
