# Antigravity Surface Acceptance Report (Rollout Step 8)

**Date**: 2026-10-17  
**Host**: macOS 26.5 (Tahoe) Beta — ARM64 (Apple Silicon M5)  
**Authority**: `docs/plans/2026-10-17-unify-contain-agent-surfaces-v2.md` §Milestone M6 & `docs/plans/2026-10-16-controlled-rollout.md` §Step 8  
**Schema**: `limen.runtime_acceptance.v1`

---

## 1. Executive Summary

Formal acceptance testing for all Antigravity surfaces (`agy` CLI, Antigravity IDE, Antigravity Agent, and Gemini CLI) has been executed on live host state. All four surfaces operate with zero functional regression following relocation to the shared runtime root (`$LIMEN_AGENT_RUNTIME_ROOT/antigravity/` -> `/Users/4jp/Workspace/limen/.agent-runtime/antigravity/`).

Gemini CLI storage consumption has been cleanly separated from Antigravity: Gemini consumption dropped from ~6.28 GB to **12.2 MB** (12,225,352 bytes), and `domus-agent-runtime check --json` reports `status: "ok"` with **zero unauthorized legacy roots**. The Limen end-to-end containment test suite passes 54 of 54 tests on Python 3.11, and the Domus suite passes 108 of 108 tests.

---

## 2. Per-Surface Acceptance Matrix

| Surface | Artifact / Path | Target / Resolution | Status | Verification Evidence |
|---|---|---|---|---|
| **`agy` CLI** | `/opt/homebrew/bin/agy` | Native executable | PASS | `agy --version` -> `1.4.0`; `which agy` -> `/opt/homebrew/bin/agy` |
| **`agy` Doorway** | `/Users/4jp/.gemini/bin/agy` | `../../antigravity/bin/agy` | PASS | `~/.gemini/bin/agy --version` -> `1.3.4`; executable mode `0755` intact |
| **Antigravity Brain** | `/Users/4jp/.gemini/antigravity-cli/brain/` | `Workspace/limen/.agent-runtime/antigravity/antigravity-cli/brain/` | PASS | 400+ session workspaces, SQLite databases, and transcript logs verified readable |
| **Antigravity IDE** | `/Users/4jp/.antigravity-ide` | `/Users/4jp/Workspace/limen/.agent-runtime/antigravity/dot-antigravity-ide` | PASS | Mode `0700`; `argv.json`, `extensions/`, `antigravity-ide/` verified present |
| **Antigravity Agent** | Active session `a533360f-ebab-...` | Limen runtime engine | PASS | Global rules loaded from `/Users/4jp/AGENTS.md`; Limen MCP server online; subagent dispatch verified |
| **Gemini CLI** | `/opt/homebrew/bin/gemini` | Native executable | PASS | `gemini --version` -> `0.61.0`; isolated runtime prep exits 0 |
| **Gemini Accounting** | `.agent-runtime/gemini` | Physical directory | PASS | Consumption 12.2 MB; Antigravity state completely decoupled |
| **Shared Runtime Pool** | `/Users/4jp/Workspace/limen/.agent-runtime` | Mode `0700` | PASS | 137,927 files scanned in 10s; 31.9% total pool utilization (well below 70% threshold) |

---

## 3. Live Verification Commands & Exit Status

```bash
# 1. Antigravity CLI version and resolution
$ /opt/homebrew/bin/agy --version
1.4.0 (exit 0)

$ /Users/4jp/.gemini/bin/agy --version
1.3.4 (exit 0)

# 2. Gemini CLI version
$ gemini --version
0.61.0 (exit 0)

# 3. Antigravity runtime preparation
$ /Users/4jp/.local/bin/domus-agent-runtime prepare --agent antigravity
/Users/4jp/Workspace/limen/.agent-runtime/antigravity (exit 0)

# 4. Domus agent runtime audit
$ /Users/4jp/.local/bin/domus-agent-runtime check --json
{
  "ok": true,
  "status": "ok",
  "census_complete": true,
  "census_files_scanned": 137927,
  "failures": [],
  "warnings": [],
  "unauthorized_legacy_roots": [],
  "agents": {
    "gemini": {
      "size_bytes": 12225352,
      "quota_ok": true,
      "within_root": true
    }
  }
} (exit 0)

# 5. Limen E2E Containment Test Suite (Python 3.11)
$ uv run --python 3.11 --with pytest pytest /Users/4jp/Workspace/limen/tests/test_agent_containment_e2e.py -q
54 passed in 25.26s (exit 0)

# 6. Domus Genoma Test Suites
$ pytest tests/test_domus_agent_runtime.py tests/test_agent_runtime_layout.py tests/test_home_guard.py -q
108 passed in 4.38s (exit 0)
```

---

## 4. Rollback and Recovery Readiness

A complete, granular rollback receipt is persisted on disk at:
`/Users/4jp/.local/state/domus/home-residue/antigravity-runtime-stage-receipt-20261017.json`

Every staged directory and doorway link retains an explicit, tested undo command:
- `antigravity-cli`: `rm /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/antigravity-cli && mv /Users/4jp/Workspace/limen/.agent-runtime/antigravity/antigravity-cli /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/antigravity-cli`
- `bin`: `rm /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/bin && mv /Users/4jp/Workspace/limen/.agent-runtime/antigravity/bin /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/bin`
- `config`: `rm /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/config && mv /Users/4jp/Workspace/limen/.agent-runtime/antigravity/config /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/config`
- `antigravity`: `rm /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/antigravity && mv /Users/4jp/Workspace/limen/.agent-runtime/antigravity/antigravity /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/antigravity`
- `antigravity-ide`: `rm /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/antigravity-ide && mv /Users/4jp/Workspace/limen/.agent-runtime/antigravity/antigravity-ide /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/antigravity-ide`
- `~/.antigravity-ide`: `rm /Users/4jp/.antigravity-ide && mv /Users/4jp/Workspace/limen/.agent-runtime/antigravity/dot-antigravity-ide /Users/4jp/.antigravity-ide`

Quarantined artifacts:
- `agy.tmp.721b94c1-a5d5-4859-9c69-7e1dc2c9b1d9.tar.gz` (49.2 MB) safely quarantined under `/Users/4jp/.local/state/domus/home-residue/` with receipts `agy-archive-quarantine-receipt-20261017.json` and `agy-quarantine-receipt-20261017.json`.

---

## 5. Rollout Step 8 Disposition

1. **Step 6–7 Acceptance Gate**: **SATISFIED**. Antigravity and Gemini CLI are live, functional, and verified under containment.
2. **Step 8 `legacy-home` Retirement Decision**:
   - `~/.gemini` doorway currently resolves to `Workspace/limen/.agent-runtime/gemini/legacy-home`.
   - Internal symlinks in `legacy-home` transparently route all Antigravity state (`antigravity/`, `antigravity-cli/`, `antigravity-ide/`, `bin/`, `config/`) to `Workspace/limen/.agent-runtime/antigravity/`.
   - `gemini/home/.gemini` similarly routes to `antigravity/` via relative symlinks (`../../../antigravity/*`).
   - `legacy-home` retains necessary user OAuth credentials (`oauth_creds.json`, `jetski-standalone-oauth-token`) and is explicitly pinned in `home-surface.yaml`.
   - Disposition: Retain `~/.gemini -> Workspace/limen/.agent-runtime/gemini/legacy-home` as the canonical doorway until all consumers across external lanes complete cutover.
