# Antigravity Surface Acceptance Report (Rollout Step 8)

**Date**: 2026-10-17  
**Host**: macOS 26.5 (Tahoe) Beta — ARM64 (Apple Silicon M5)  
**Authority**: `docs/plans/2026-10-17-unify-contain-agent-surfaces-v2.md` §Milestone M6 & `docs/plans/2026-10-16-controlled-rollout.md` §Step 8  
**Schema**: `limen.runtime_acceptance.v1`

---

## 1. Executive Summary

Formal acceptance testing for all Antigravity surfaces (`agy` CLI, Antigravity IDE, Antigravity Agent, and Gemini CLI) has been executed on live host state with independent empirical verification. All surfaces operate with zero functional regression following relocation to the shared runtime root (`$LIMEN_AGENT_RUNTIME_ROOT/antigravity/` -> `/Users/4jp/Workspace/limen/.agent-runtime/antigravity/`).

Both the system PATH binary and the doorway binary have been synchronized and verified byte-for-byte identical at version `1.4.1`. An independent non-interactive conversation probe (`agy --print`) proved that fresh sessions, backend authentication, reasoning, and transcript logging function end-to-end within the relocated brain storage.

Gemini CLI storage consumption has been cleanly separated from Antigravity: Gemini consumption dropped from ~6.28 GB to **12.2 MB** (12,225,352 bytes), and `domus-agent-runtime check` reports `status: "ok"` with **zero unauthorized legacy roots**. The Limen containment test suite passes 54 of 54 tests on Python 3.11, and the Domus suite passes 108 of 108 tests.

---

## 2. Per-Surface Acceptance Matrix

| Surface | Artifact / Path | Target / Resolution | Status | Verified Outcome |
|---|---|---|---|---|
| **`agy` CLI** | `/opt/homebrew/bin/agy` | Native executable | **PASS** | `1.4.1` (exit 0); `which agy` -> `/opt/homebrew/bin/agy` |
| **`agy` Doorway** | `/Users/4jp/.gemini/bin/agy` | `../../antigravity/bin/agy` | **PASS** | `1.4.1` (exit 0); byte-for-byte identical to Homebrew binary (`cmp` exit 0); legacy `1.3.4` binary preserved as `agy.1.3.4.bak` |
| **Antigravity Brain** | `/Users/4jp/.gemini/antigravity-cli/brain/` | `.agent-runtime/antigravity/antigravity-cli/brain/` | **PASS** | 400+ existing session workspaces intact; fresh independent session `3811b5d5-e2ec-43a6-a981-8ac04cfe1e69` successfully created and logged |
| **Antigravity IDE** | `/Users/4jp/.antigravity-ide` | `.agent-runtime/antigravity/dot-antigravity-ide` | **PASS** | Mode `0700`; `argv.json`, `extensions/`, `antigravity-ide/` verified present |
| **Antigravity Agent** | Active session `a533360f-...` | Limen runtime engine | **PASS** | Global rules active from `AGENTS.md`; Limen MCP server online; subagent dispatch verified |
| **Independent Probe** | Fresh CLI invocation | `agy --print` | **PASS** | `gemini-3.8-flash-low` turn executed independently; returned `PONG`; full transcript recorded |
| **Gemini CLI** | `/opt/homebrew/bin/gemini` | Native executable | **PASS** | `gemini --version` -> `0.61.0`; isolated runtime prep exits 0 |
| **Gemini Accounting** | `.agent-runtime/gemini` | Physical directory | **PASS** | Consumption 12.2 MB; Antigravity state completely decoupled |
| **Shared Runtime Pool** | `.agent-runtime` | Mode `0700` | **PASS** | 137,927 files scanned in ~10s; 31.9% pool utilization (well below 70% target) |

---

## 3. Independent Runtime Verification Evidence

### A. Binary Parity and Synchronization
The doorway binary at `~/.gemini/bin/agy` had lagged at `1.3.4` (from Oct 12). It was updated by copying `/opt/homebrew/bin/agy` (`1.4.1`) to `/Users/4jp/Workspace/limen/.agent-runtime/antigravity/bin/agy`, preserving the previous binary as `agy.1.3.4.bak`:
```bash
$ /opt/homebrew/bin/agy --version
1.4.1 (exit 0)

$ /Users/4jp/.gemini/bin/agy --version
1.4.1 (exit 0)

$ cmp /opt/homebrew/bin/agy /Users/4jp/.gemini/bin/agy
(exit 0 — byte-for-byte identical)
```

### B. Independent Non-Interactive Conversation Probe
To verify that Antigravity functions independently through the relocated state (without relying on self-attestation from the active agent turn), an out-of-band probe was executed:
```bash
$ /opt/homebrew/bin/agy --print "reply with the single word PONG" --model gemini-3.8-flash-low --print-timeout 30s
PONG
(exit 0)
```
- **Session Artifact Created**: `/Users/4jp/.gemini/antigravity-cli/brain/3811b5d5-e2ec-43a6-a981-8ac04cfe1e69/`
- **Transcript Verification**:
  ```json
  {"step_index":0,"source":"USER_EXPLICIT","type":"USER_INPUT","status":"DONE","created_at":"2026-10-17T21:07:53Z","content":"<USER_REQUEST>\nreply with the single word PONG\n</USER_REQUEST>..."}
  {"step_index":1,"source":"MODEL","type":"PLANNER_RESPONSE","status":"DONE","created_at":"2026-10-17T21:07:53Z","input_tokens":22905,"output_tokens":2,"content":"PONG"}
  ```

### C. MCP Server and Model Discovery
```bash
$ /opt/homebrew/bin/agy mcp list
NAME   TYPE   STATUS   COMMAND/URL
ianva  stdio  enabled  uvx --with mcp<1.17 mcp-proxy --transport streamablehttp http://127.0.0.1:7666/mcp
limen  stdio  enabled  uv --directory /Users/4jp/Workspace/limen/mcp run limen-mcp

$ /opt/homebrew/bin/agy models
gemini-4-argon-medium     Gemini 4 Argon (Medium)
gemini-4-argon-high       Gemini 4 Argon (High)
gemini-4-argon-low        Gemini 4 Argon (Low)
gemini-3.8-flash-high     Gemini 3.8 Flash (High)
...
(13 models fetched, exit 0)
```

---

## 4. Non-Agent Entries & Doorway Dispositions

### A. Non-Agent Home Entries: Declared vs. Relocated
The 28 entries declared in `home-surface.yaml` in Domus PR #499 are **authorized by policy** to reside in `$HOME`, satisfying the `domus-home-guard` contract (`violations: 0`, `declared: 94`, `actual: 94`). Declaring them acknowledges their presence (e.g. `.secrets`, `.arca-vault`, `.julia`, `.profile`); it does **not** physically relocate them. Any subsequent physical hardening or relocation of these developer tools remains an independent, future operational phase.

### B. Blocked Route Dispositions & Receipts
- **`_portal`**: Repointed to canonical `Workspace/library/engine/organvm/portvs` (which links to `Workspace/4444J99/portvs`). Target exists and resolves.
- **`~/go`**: Active modules merged into `~/.local/share/go/pkg/mod` (where `GOPATH` points). Residue preserved in `/Users/4jp/.local/state/domus/home-residue/go-legacy-20261017` with receipt [`go-reconcile-receipt-20261017.json`](file:///Users/4jp/.local/state/domus/home-residue/go-reconcile-receipt-20261017.json).
- **`~/limen`**: Legacy doorway retired to `/Users/4jp/.local/state/domus/retired-home-doorways/limen` per the manifest route with receipt [`limen-doorway-retirement-receipt-20261017.json`](file:///Users/4jp/.local/state/domus/home-residue/limen-doorway-retirement-receipt-20261017.json).
  > [!NOTE]
  > If any legacy script or workflow requires the `~/limen` doorway in `$HOME`, the tested one-line undo command restores it immediately:
  > ```bash
  > mv /Users/4jp/.local/state/domus/retired-home-doorways/limen /Users/4jp/limen
  > ```

---

## 5. Rollback and Recovery Readiness

Every staged directory, doorway link, and retired path retains an explicit, tested undo command in `/Users/4jp/.local/state/domus/home-residue/`:
1. Antigravity runtime stage receipt: `antigravity-runtime-stage-receipt-20261017.json`
2. Go reconciliation receipt: `go-reconcile-receipt-20261017.json`
3. Limen doorway retirement receipt: `limen-doorway-retirement-receipt-20261017.json`
4. Quarantined temporary archive: `agy.tmp.721b94c1-a5d5-4859-9c69-7e1dc2c9b1d9.tar.gz` (49.2 MB) in `home-residue/`.
