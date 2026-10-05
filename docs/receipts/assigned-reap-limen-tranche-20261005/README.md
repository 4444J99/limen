# Assigned Reap Lifecycle Receipt — Limen Tranche (2026-10-05)

## Overview & Operator Authorization
This reap tranche was executed under explicit operator assignment of four exact target paths:
- `/Users/4jp/Workspace/limen/mcp`
- `/Users/4jp/Workspace/organvm/limen`
- `/Users/4jp/limen-lanes/agy/limen`
- `/Users/4jp/Workspace/limen`

Bound truthfully in [`scope.json`](scope.json) under schema `limen.worktree_reclaim_scope.v1`, on PR rail [PR #2832](https://github.com/4444J99/limen/pull/2832).

---

## Target Results Summary

| Target Path | Initial Footprint | Final Footprint | Status | Result / Retention Blocker |
| :--- | :--- | :--- | :--- | :--- |
| `/Users/4jp/Workspace/organvm/limen` | 199,768 KB | 0 KB | **REAPED** | Clean clone; all 4 branches and 2 tags verified live-remote exact; editor state and logs quarantined; purged via `purge_remote_proven_path` |
| `/Users/4jp/limen-lanes/agy/limen` | 296,544 KB | 0 KB | **REAPED** | Clean clone; unique branch `fix/self-heal-retirement-predicate` preserved to origin; editor state and logs quarantined; caches cleaned; purged via `purge_remote_proven_path`; parent `agy/` removed |
| `/Users/4jp/Workspace/limen/mcp` | 35,012 KB | 208 KB | **HELD** | Subdirectory of active live checkout; tracked files required for MCP tooling in active session; 34,804 KB reconstructible caches cleaned |
| `/Users/4jp/Workspace/limen` | 39,221,228 KB | 39,221,228 KB | **HELD** | Active working directory and live checkout for current agent session (`_SELF_GUARD`) |

**Direct Target Footprint Reclaimed**: **531,116 KB** (~531 MB).

---

## Detailed Directory Breakdown

### 1. `/Users/4jp/Workspace/organvm/limen` (REAPED)
- **Classification**: Standalone Git clone of `https://github.com/4444J99/limen.git`.
- **Remote Parity Verification**:
  - HEAD `74505dddaad6892fd101dee0928bda44166b3d21` verified on `origin/main` (commit #2618).
  - All local branches verified against live remote origin:
    - `4444j99-plan-requested-change` (`bee0bbb352`): on `origin/feat/branch-family-governance` and `origin/preserve/organvm-4444j99-plan-requested-change-20261003`
    - `fix/inventory-admission-2606` (`fb30e77d46`): on `origin/successor/git-finishline-20260910`
    - `fix/inventory-admission-2608` (`54d264bd4a`): on `origin/fix/finishline-refund-count-20260910`
    - `main` (`74505dddaa`): on `origin/main`
  - Local tags verified against remote: `archive/pr-2543-detached-67afecedd1ab-20260828`, `v0.1.0`.
  - Live remote ref proof: Verified via `all_local_refs_remote_proof` (returned True).
- **Preservation & Quarantine**:
  - `.recode/changes.db`: Quarantined to `_limen-worktree-abandonment/editor-state-organvm-limen-recode-1791057705` (receipt: `2710317a5c611a3e1960b152ba61becafb8262c48c49f841edbc9accda8097ec.json`).
  - `logs/reap-branches.jsonl`: Quarantined to `_limen-worktree-abandonment/generated-organvm-limen-logs-reap-branches-1790251628.jsonl` (receipt: `9f94b9438873f514107e88003f4f674ea9cb891ba542d713201efea46d32d00c.json`).
  - Tracked `.gitignore`: Reverted 3-line editor edit (`.recode`).
- **Reap Action**: Purged via `purge_remote_proven_path` with fresh content probe; typed abandonment receipt: `c1ef0bec2583891e707830116a1797b323b83396822929513c7f5ec4909a0cd9.json`.
- **Post-Reap Status**: Directory is completely absent (`Target exists: False`).

---

### 2. `/Users/4jp/limen-lanes/agy/limen` (REAPED)
- **Classification**: Standalone Git clone of `https://github.com/4444J99/limen.git`.
- **Remote Parity & Work Preservation**:
  - Unique local work identified: branch `fix/self-heal-retirement-predicate` at commit `6bd0b3c208a392d61b63058647392d3710af3078` ("fix(self-heal): root-cause HEAL task retirement gap and add executable predicate gate").
  - Pushed branch to remote `origin`: `refs/heads/preserve/agy-fix-self-heal-retirement-predicate`.
  - Verified remote parity on live GitHub origin via `git ls-remote` (exact SHA match).
  - HEAD `a26cdf18c3b5a94b9761938eab6358daced0ba73` verified on `origin/main` (commit #2148).
  - All local branches and tags verified live remote exact via `all_local_refs_remote_proof`.
- **Preservation & Quarantine**:
  - `.recode/changes.db`: Quarantined to `_limen-worktree-abandonment/editor-state-agy-limen-recode-1791057705` (receipt: `66dbf77d11f104644ddf046cd52ec0b248c1d19280d28b87baa219ffb6fe19c9.json`).
  - `logs/await-pr.log`: Quarantined to `_limen-worktree-abandonment/generated-agy-limen-logs-await-pr-1786278833.log` (receipt: `da7925f41ba4452030f9238079b8f6826cf616ee71fa69d601c6fee6d6344c2a.json`).
  - `logs/tabularius-organ-state.json`: Quarantined to `_limen-worktree-abandonment/generated-agy-limen-logs-tabularius-organ-state-1786278833.json` (receipt: `fab4fd2be31bc036a7eec4acd4fb540a8011eb67f845aaa486de5a272196f4c4.json`).
  - Caches cleaned: `.mypy_cache`, `.ruff_cache`, `cli/.mypy_cache`, `cli/.pytest_cache`, `cli/src/limen.egg-info`, `__pycache__` (all proven reconstructible from committed `pyproject.toml` and `uv.lock`).
  - Tracked `.gitignore`: Reverted 3-line editor edit (`.recode`).
- **Reap Action**: Purged via `purge_remote_proven_path` with fresh content probe; typed abandonment receipt: `310c21257129b75f322c10ee73a383af8b6a57334de786b22a1338be4852babb.json`.
- **Parent Directory**: Empty parent `/Users/4jp/limen-lanes/agy` reaped via `rmdir` (`Target exists: False`).

---

### 3. `/Users/4jp/Workspace/limen/mcp` (HELD)
- **Classification**: Non-Git directory (subdirectory within parent Git repository `/Users/4jp/Workspace/limen`).
- **Inspection & Payloads**:
  - Tracked source files: `pyproject.toml`, `src/limen_mcp/intake.py`, `src/limen_mcp/py.typed`, `src/limen_mcp/runtime_requirements.py`, `src/limen_mcp/server.py`, `uv.lock`. All are clean (0 diff), committed to `main` at `HEAD`, and verified on `origin/main`.
  - Reconstructible tool caches: `.venv` (34,804 KB virtualenv), `.mypy_cache`, `__pycache__`, `.recode` (empty 28KB editor db).
- **Reclamation Action**:
  - Reconstructible tool caches safely removed to recover disk space. Footprint reduced from 35,012 KB down to 208 KB (reclaimed 34,804 KB).
  - Directory retained under parent dependency hold: Deleting `mcp/` would remove clean tracked source files required by the active session and IDE MCP harness.
- **Blocker**: Parent checkout active session dependency.
- **Owner**: Operator / active workspace session.
- **Next Action**: Directory will be reaped when parent checkout `/Users/4jp/Workspace/limen` is released.

---

### 4. `/Users/4jp/Workspace/limen` (HELD)
- **Classification**: Active live checkout and git repository root.
- **Inspection & Payloads**:
  - Contains active session runtime, developer harness, and current working directory.
  - Protected under `_SELF_GUARD` and `AGENTS.md` direct-session protocol.
- **Blocker**: Active `self/live-checkout` session running developer harness and current turn.
- **Owner**: Operator / active session harness.
- **Next Action**: Session closeout; release checkout following session migration or repo retirement.

---

## Artifact Index
- Scope Manifest: [`scope.json`](scope.json) (`limen.worktree_reclaim_scope.v1`)
- Durable Receipt: [`receipt.json`](receipt.json) (`limen.reap_receipt.v1`)
- Abandonment Receipts:
  - [`c1ef0bec2583891e...json`](abandonment-receipts/c1ef0bec2583891e707830116a1797b323b83396822929513c7f5ec4909a0cd9.json) (`purge-proven-path` for `organvm/limen`)
  - [`310c21257129b75f...json`](abandonment-receipts/310c21257129b75f322c10ee73a383af8b6a57334de786b22a1338be4852babb.json) (`purge-proven-path` for `agy/limen`)
  - [`2710317a5c611a3e...json`](abandonment-receipts/2710317a5c611a3e1960b152ba61becafb8262c48c49f841edbc9accda8097ec.json) (quarantine `organvm/limen` `.recode`)
  - [`9f94b9438873f514...json`](abandonment-receipts/9f94b9438873f514107e88003f4f674ea9cb891ba542d713201efea46d32d00c.json) (quarantine `organvm/limen` `reap-branches.jsonl`)
  - [`66dbf77d11f10464...json`](abandonment-receipts/66dbf77d11f104644ddf046cd52ec0b248c1d19280d28b87baa219ffb6fe19c9.json) (quarantine `agy/limen` `.recode`)
  - [`da7925f41ba44520...json`](abandonment-receipts/da7925f41ba4452030f9238079b8f6826cf616ee71fa69d601c6fee6d6344c2a.json) (quarantine `agy/limen` `await-pr.log`)
  - [`fab4fd2be31bc036...json`](abandonment-receipts/fab4fd2be31bc036a7eec4acd4fb540a8011eb67f845aaa486de5a272196f4c4.json) (quarantine `agy/limen` `tabularius-organ-state.json`)
