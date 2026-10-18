# Plan v2: Unify and Contain All Agent Directories & Files (Provider-Agnostic)

Issue: #2848
PR: #2925

- **Date**: 2026-10-17
- **Slug**: `unify-contain-agent-surfaces-v2`
- **Supersedes**: `2026-10-17-unify-contain-agent-surfaces.md` (v1 retained unmodified)
- **Git-Tracked Home**: `/Users/4jp/Workspace/limen/docs/plans/2026-10-17-unify-contain-agent-surfaces-v2.md`
- **Runtime Mirror**: `/Users/4jp/Workspace/limen/.agent-runtime/claude/plans/2026-10-17-unify-contain-agent-surfaces-v2.md`
- **Status**: Revised after Claude + Codex cross-agent review and live SQLite/byte-diff verification

---

## 0. Reasoned Disposition of Cross-Agent Review Feedback (Claude & Codex)

Per `~/AGENTS.md` (*Reasoned disposition of review feedback* & *No-stall*), all critique items from Claude and Codex were evaluated against live disk state and executed as read-only verifications immediately:

| # | Reviewer Finding | Disposition | Live Verification Evidence & Plan v2 Change |
| :- | :--- | :--- | :--- |
| 1 | **Misquoted Audit Finding #4** (Claude & Codex): `2026-10-16-agent-audit-report.md:10,:39` blames skill-list truncation on 18 Desktop inline plugins and ~12 claude.ai connectors, not a ">50 skills" threshold. | **ACCEPT** | Corrected in §1 & §4.3. Removed the arbitrary 30-skill cap. Skill unification now deduplicates by SHA-256 content/provenance first, preserves all capabilities, and defers default-on subset pruning to Step 8 of `2026-10-16-controlled-rollout.md` using the 90-day non-invocation rule in `canonical-surfaces-reference.md:17`. |
| 2 | **Relative Symlink Depth Error** (Codex): From `gemini/home/.gemini/`, `../../antigravity` resolves to `gemini/antigravity/`, not `$LIMEN_AGENT_RUNTIME_ROOT/antigravity/` (`../../../antigravity`). | **ACCEPT** | Corrected in §4.2. All doorway links must be computed programmatically and verified with `Path.resolve(strict=True)` against the target inode rather than hand-written `..` segments. |
| 3 | **Rollout Gate Sequencing** (Claude & Codex): `2026-10-16-controlled-rollout.md:9,:30` gates the `gemini/legacy-home` retirement and default-on skill subset at Step 8 (after Steps 6–7 per-runtime acceptance). | **ACCEPT** | Resequenced in §4. Phase 2 stages `$LIMEN_AGENT_RUNTIME_ROOT/antigravity/` additively and keeps the `~/.gemini -> gemini/legacy-home` doorway intact until Steps 6–7 acceptance passes. |
| 4 | **Don't Blindly Delete `~/.gemini/bin/agy*` (230 MB)** (Claude & Codex): `agy.tmp.*.tar.gz` indicates an internal self-updater; deleting `bin/agy` may break or re-trigger self-update. | **ACCEPT** | Live check of `~/.gemini/antigravity-cli/updater/update_status.json` (`{"success":true,"message":"Already on the latest version."}`, mtime `2026-10-17T11:32`) confirms Antigravity's updater manages this path. Changed to quarantine-first (move `agy.tmp.*.tar.gz` to `.local/state/domus/home-residue/` with SHA-256 receipt; leave `bin/agy` intact until updater behavior is verified). |
| 5 | **`~/.local/share/codex` Needs Database-Level Comparison, Not Just `tmp/`** (Claude & Codex): Check SQLite tables, `history.jsonl`, and `.codex/plans/2026-10-17-codex-native-lineage.md`. | **ACCEPT (Verified Live)** | Executed read-only SQLite primary-key set-difference (`verify-review-items.sh`): **`~/.local/share/codex` has ZERO thread overlap with `$CODEX_HOME`** (`state_5.sqlite`: **2,688 threads only in old** vs 1,554 only in new; `thread_history_1.sqlite`: **442 threads only in old**; `memories_1.sqlite`: **247 rows only in old**; `goals_1.sqlite`: **30 rows only in old**). Also verified `.codex/plans/2026-10-17-codex-native-lineage.md` (scopes `transcript_witness` header validation on `fix/codex-native-lineage-20261017`). Updated Phase 1B: `~/.local/share/codex` is a distinct historical epoch requiring full custody staging + SQLite/JSONL restoration proof before retirement. |
| 6 | **`~/.claude.json` Live Contention & Copy-First Receipt** (Claude & Codex): Verify diff before relinking `~/.claude.json`. | **ACCEPT (Verified Live)** | Executed byte comparison: `/Users/4jp/.claude.json` (95,080 bytes, mtime `2026-10-16T13:56:02`) is **byte-for-byte identical (`diff_lines: 0`)** to `$CLAUDE_CONFIG_DIR/legacy-home.json`. Active Claude Code sessions write to `$CLAUDE_CONFIG_DIR/.claude.json` (103,788 bytes, mtime `2026-10-17T12:06:53`), NOT `~/.claude.json`. Phase 1A still performs a copy-first backup receipt before restoring the symlink. |
| 7 | **Refresh `chezmoi` Status Today** (Codex): Yesterday's 8-target preview (`2026-10-16-insights-chezmoi-apply-preview.md`) may already be applied. | **ACCEPT (Verified Live)** | Executed `chezmoi status` & `git log` in `domus-genoma`: `HEAD` is now `94ed4c76` (PR #476; PR #459 merged & applied per `docs/receipts/2026-10-17-codex-doctor-heal.md`). All 8 targets from yesterday's preview are **already applied (`0` drift)**. Only `gemini/legacy-home/config/AGENTS.md` (`M`, +6-line shared-context pointer) and `codex/config.toml` (`MM`) have pending status. |
| 8 | **Unclaimed Scope: `shared/plans/` & Repo-Wide `.agents/`** (Claude & Codex): Moving per-agent `plans/` mutates `~/AGENTS.md` Plan Discipline; `s-02-plan` writes to gitignored `.agent-runtime/claude/plans/`. | **ACCEPT** | Removed `shared/plans/` migration from containment phases; kept per-agent `plans/` per `~/AGENTS.md`. Added a targeted fix for the `s-02-plan` skill defect so plans are persisted to git-tracked `docs/plans/` or `<repo>/.claude/plans/`. Scoped repo-wide `.agents/` conversion as a separate opt-in track. |
| 9 | **Consumer Matrix Must Include All Providers** (Codex): Don't claim parity from a 5-agent probe while omitting Cursor and Copilot. | **ACCEPT** | Added an explicit 8-Consumer Verification Matrix (§6) covering `claude`, `codex`, `gemini`, `agy`, `opencode`, `copilot`, `cursor`, and `claude-desktop`. |

---

## 1. Context & Live Evidence Summary (2026-10-17)

1. **Current `domus-genoma` & `chezmoi` State**:
   - `domus-genoma` `main` is at `94ed4c76` (`feat(hooks): enforce subagent model tiering across agents (#476)`).
   - Host writer lease (`limen/scripts/host-work-admission.py status --no-probe`) is **clear (`allowed: true`, `leases: []`, `swap_fraction: 0.150`)**.
   - Yesterday's 8 targets from `2026-10-16-insights-chezmoi-apply-preview.md` are **already applied and clean**. Only `Workspace/limen/.agent-runtime/gemini/legacy-home/config/AGENTS.md` (`M`, 6-line shared-context addendum) and `Workspace/limen/.agent-runtime/codex/config.toml` (`MM`) show drift in `chezmoi status`.
2. **Why `domus-agent-runtime check` Is Blocked (`unauthorized_legacy_roots: 2`)**:
   - **`/Users/4jp/.claude.json` (95,080 bytes)**: Regular file in `$HOME`, verified **byte-identical** to `/Users/4jp/Workspace/limen/.agent-runtime/claude/legacy-home.json` (`mtime: 2026-10-16T13:47:43`). Live Claude Code writes to `$CLAUDE_CONFIG_DIR/.claude.json` (103,788 bytes), not `~/.claude.json`.
   - **`/Users/4jp/.local/share/codex` (3.29 GB)**: Inactive (`lsof` = 0 open files; last touched `2026-10-16T14:47`), but SQLite table inspection proved it holds a **completely disjoint historical epoch** from `$CODEX_HOME`:
     - `state_5.sqlite` (`threads`): **2,688 unique historical threads** (0 in `$CODEX_HOME`).
     - `thread_history_1.sqlite`: **442 unique thread projections** (12,143 items, 269 turns; 0 in `$CODEX_HOME`).
     - `memories_1.sqlite`: **247 unique `stage1_outputs`** (0 in `$CODEX_HOME`).
     - `goals_1.sqlite`: **30 unique `thread_goals`** (0 in `$CODEX_HOME`).
     - `logs_2.sqlite`: 1.32 GB (1,439 log rows).
3. **Uncontained Vendor Directories in `$HOME` (~1.84 GB across 16 entries)** & **`domus-home-guard` Violations (55 total)**:
   - Declared `application` directories still physically in `$HOME`: `~/.github-copilot-cli` (757 MB), `~/.copilot` (286 MB), `~/.antigravity-ide` (86 MB), `~/.serena` (65 MB), `~/.claude-server-commander` (6.1 MB), `~/.cline` (1.0 MB, uninstalled), `~/.ollama` (496 KB), `~/.jules` (16 KB).
   - Undeclared agent/tool directories failing `domus-home-guard`: `~/.cursor` (46 MB), `~/teamwork_projects` (1.0 MB), `~/.grokbot` (188 KB), `~/.opencode` (68 KB), `~/.agent-browser` (36 KB), `~/bound` (28 KB), `~/.desktop-commander-device` (4 KB), `~/.mcp-auth` (0 B).
   - Ready `route_pending` actions in `home-surface.yaml`: `.claude.json.{bak,tmp}*` (3 files), `.gitconfig.bak-testfixture-20260724`, `.card-trade-social`, `.media-ark`, `nltk_data`, `dummy-remote.git`, `markdown-document-memory`, `wb-weave-demo`, `value-repos.json`.
4. **Skills Split-Brain Across 6 Directories**:
   - `~/.agents/skills` (27 Chezmoi-managed skills), `$LIMEN_AGENT_RUNTIME_ROOT/.agents/skills` (28 skills invisible to Antigravity/Claude/Gemini), `$CLAUDE_CONFIG_DIR/skills` (4 symlinks + `.trash` + `synced`), `$CODEX_HOME/skills` (11 entries), `$GEMINI_CLI_HOME/.gemini/skills` (4 symlinks), and `~/.config/opencode/skills` (4 symlinks).

---

## 2. Goal

Achieve **verified, reversible containment** across all agent providers on this host so that:
1. Every active agent instruction, skill, hook, and runtime directory has a single declared owner and rollback receipt.
2. Historical state in `~/.local/share/codex` (2,688 threads) and `~/.claude.json` is preserved with cryptographic custody before any legacy path is retired or relinked.
3. All 8 agent consumers (`claude`, `codex`, `gemini`, `agy`, `opencode`, `copilot`, `cursor`, `claude-desktop`) pass an explicit discovery, invocation, state-continuity, and rollback verification matrix.

---

## 3. Target 4-Ring Containment Architecture

1. **Ring 0 — Provider-Agnostic Governance & Shared Catalogs**:
   - **Liturgy & Reliquary**: `~/.config/ai-context/AGENTS.md` → `~/AGENTS.md` + `~/.config/ai-context/reliquary/`.
   - **Skills Hub**: `~/.agents/skills/` (Chezmoi-deployed + `domus-agent-skills` catalog links) + `$LIMEN_AGENT_RUNTIME_ROOT/shared/skills-catalog/` (preserving all deduplicated skills from `$LIMEN_AGENT_RUNTIME_ROOT/.agents/skills/`).
   - **Plan Durability Fix**: Update `s-02-plan` (`dot_agents/skills/s-02-plan/SKILL.md` in `domus-genoma`) so home-CWD plans write to a git-tracked surface (`$LIMEN_ROOT/docs/plans/` or `$DOMUS_ROOT/docs/plans/`) in addition to the runtime mirror, preventing gitignored-only plans.
2. **Ring 1 — Contained Vendor Runtimes (`$LIMEN_AGENT_RUNTIME_ROOT/<provider>/`)**:
   - Native env-relocated runtimes: `claude/` (`$CLAUDE_CONFIG_DIR`), `codex/` (`$CODEX_HOME`), `gemini/home/` (`$GEMINI_CLI_HOME`), `opencode/` (`XDG_DATA/STATE/CACHE_HOME`).
   - Doorway-routed runtimes (`preserve-and-link` in `home-surface.yaml`): `antigravity/` (staged for Step 8 cutover), `copilot/`, `cursor/`, and `aux/{serena,ollama,agent-browser,claude-server-commander,desktop-commander-device,mcp-auth,jules}/`.
3. **Ring 2 — OS-Fixed Desktop Bundles (`~/Library/{Application Support,Caches,Logs}`)**:
   - Never symlinked (preserving macOS TCC, Electron `ShipIt`, and codesign integrity).
   - Governed via `application_objects` in `home-surface.yaml`, bounded by `domus-agent-maintain`, and excluded from cloud backup churn via `domus-backblaze-exclusions`.
4. **Ring 3 — Per-Repository Project Surfaces (`<repo>/`)**:
   - Keep existing per-tool `<repo>/.<tool>/plans/` contract intact until an explicit `~/AGENTS.md` amendment is proposed and approved.

---

## 4. Phased Implementation Plan

### Phase 1A — Reconcile `gemini/legacy-home/config/AGENTS.md` & `~/.claude.json` (Immediate, Reversible)
1. **Apply the single clean Chezmoi target for Antigravity's shim**:
   - Run `chezmoi apply /Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/config/AGENTS.md` (adds the 6-line `context-index.md` pointer; already verified via `chezmoi diff`).
2. **Copy-first backup and symlink restoration for `~/.claude.json`**:
   - Verify no process holds `/Users/4jp/.claude.json` open (`lsof /Users/4jp/.claude.json`) and re-verify `cmp -s /Users/4jp/.claude.json /Users/4jp/Workspace/limen/.agent-runtime/claude/legacy-home.json`.
   - Copy `/Users/4jp/.claude.json` to `/Users/4jp/.local/state/domus/home-residue/.claude.json.pre-relink-20261017` and record a JSON receipt (`previous_kind`, `sha256`, `inode`, `rollback_cmd`) in `/Users/4jp/.local/state/domus/home-residue/claude-json-relink-receipt-20261017.json`.
   - Atomically replace `/Users/4jp/.claude.json` with a symlink to `Workspace/limen/.agent-runtime/claude/legacy-home.json` (matching `home-surface.yaml` line 237).
   - Move the 3 `.claude.json.{bak,tmp}*` files into `/Users/4jp/.local/state/domus/home-residue/` per their declared `home-surface.yaml` routes.
- **Output**: `~/.claude.json` removed from `domus-agent-runtime check` `unauthorized_legacy_roots` and from `domus-home-guard` violations, with a one-command rollback receipt.

### Phase 1B — Custody-Stage and Verify `~/.local/share/codex` (3.29 GB, 2,688 Historical Threads)
1. **Stage to `$LIMEN_CUSTODY_STAGING_ROOT` (`/Users/4jp/Workspace/limen/.limen-private/custody-staging`)**:
   - Create a mode-`0700` run directory `$LIMEN_CUSTODY_STAGING_ROOT/codex-legacy-share-20261017T<UTC>/`.
   - Use APFS copy-on-write clone (`cp -Rc`) on `/dev/disk3s5` (consuming **0 additional physical blocks**) to stage `state_5.sqlite` (2,688 threads), `thread_history_1.sqlite` (442 threads), `memories_1.sqlite` (247 stage1 outputs), `goals_1.sqlite` (30 goals), `history.jsonl` (1,941 lines), `sessions/`, `archived_sessions/`, `plans/`, `auth.json`, `config*.toml`, and `tmp/` / `.tmp/`.
2. **Prove Restoration & Satisfy `managed_store_surfaces` Retirement Requirements**:
   - Verify SHA-256 manifest of all staged files and run `PRAGMA integrity_check` + row-count verification on the staged SQLite copies.
   - Check `.local/share/codex/tmp` and `.local/share/codex/.tmp` against the 4 retirement predicates in `home-surface.yaml` lines 64–84.
   - Only after custody receipt and restoration proof pass, retire `~/.local/share/codex` so `domus-agent-runtime check` exits `0`.
- **Output**: Custody manifest + restoration proof in `$LIMEN_CUSTODY_STAGING_ROOT`; `domus-agent-runtime check` = `ok`.

### Phase 2 — Stage Antigravity (`agy`) Containment & Quarantine Updater Temp (Gated on Rollout Step 8)
1. **Quarantine stale temp archive (not the binary)**:
   - Move `/Users/4jp/.gemini/bin/agy.tmp.721b94c1-a5d5-4859-9c69-7e1dc2c9b1d9.tar.gz` (49.2 MB, Oct 13) to `/Users/4jp/.local/state/domus/home-residue/` with a SHA-256 receipt. Keep `/Users/4jp/.gemini/bin/agy` in place while observing Antigravity's updater across one update cycle.
2. **Prepare `$LIMEN_AGENT_RUNTIME_ROOT/antigravity/` additively**:
   - In a `domus-genoma` worktree PR (respecting the writer lease), add `antigravity` support to `domus-agent-runtime.py` and `home-surface.yaml` (routing `~/.antigravity-ide` → `Workspace/limen/.agent-runtime/antigravity/dot-antigravity-ide`).
   - Hold the cutover of `~/.gemini` (`legacy-home` → `gemini/home` with `../../../antigravity/*` relative symlinks verified via `Path.resolve(strict=True)`) until Steps 6–7 of `2026-10-16-controlled-rollout.md` complete.
- **Output**: 49.2 MB temp archive quarantined with receipt; Antigravity containment PR staged for Step 8 cutover.

### Phase 3 — Reconcile Skills by Content & Fix `s-02-plan` Durability
1. **Content-Hash & Provenance Reconciliation of the 6 Skills Roots**:
   - Run a read-only inventory comparing SHA-256 hashes, frontmatter, and dependencies across `~/.agents/skills` (27), `$LIMEN_AGENT_RUNTIME_ROOT/.agents/skills` (28), and `a-i--skills` (`~/.local/share/ai-skills/current`).
   - Identify exact duplicates (e.g., `source-command-g-omega` vs `g-omega`, `source-command-s-00-phase` vs `s-00-phase`), preserve all unique skills in `$LIMEN_AGENT_RUNTIME_ROOT/shared/skills-catalog/`, and register them in `skills-registry.json` (`a-i--skills`) before any pruning at Rollout Step 8.
2. **Fix `s-02-plan` Git-Ignore Defect**:
   - Submit a `domus-genoma` PR updating `dot_agents/skills/s-02-plan/SKILL.md` so when `git rev-parse --show-toplevel` fails (e.g. CWD is `~`), the skill writes the canonical plan to `$LIMEN_ROOT/docs/plans/YYYY-MM-DD-${slug}.md` (git-tracked) and mirrors to `$LIMEN_AGENT_RUNTIME_ROOT/claude/plans/`.
- **Output**: Zero orphaned skills; `s-02-plan` no longer strands plans in a gitignored directory.

### Phase 4 — Contain Remaining `$HOME` Vendor Directories via `domus-home-guard`
1. **Declare and route the remaining `$HOME` entries in `home-surface.yaml` (via `domus-genoma` PR)**:
   - **Retire uninstalled/orphan dirs to `.local/state/domus/home-residue/`**: `~/.cline` (1.0 MB), `~/.grokbot` (188 KB), `~/teamwork_projects` (1.0 MB), `~/.opencode` (68 KB, after verifying it has no state newer than `$LIMEN_AGENT_RUNTIME_ROOT/opencode`).
   - **Add `preserve-and-link` doorways into `$LIMEN_AGENT_RUNTIME_ROOT/`** (guarded by `_exact_process_active()` == 0):
     - `~/.copilot` → `Workspace/limen/.agent-runtime/copilot/dot-copilot`
     - `~/.github-copilot-cli` → `Workspace/limen/.agent-runtime/copilot/dot-github-copilot-cli`
     - `~/.cursor` → `Workspace/limen/.agent-runtime/cursor/dot-cursor`
     - `~/.serena` → `Workspace/limen/.agent-runtime/aux/serena`
     - `~/.ollama` → `Workspace/limen/.agent-runtime/aux/ollama`
     - `~/.agent-browser` → `Workspace/limen/.agent-runtime/aux/agent-browser`
     - `~/.claude-server-commander` → `Workspace/limen/.agent-runtime/aux/claude-server-commander`
     - `~/.desktop-commander-device` → `Workspace/limen/.agent-runtime/aux/desktop-commander-device`
     - `~/.mcp-auth` → `Workspace/limen/.agent-runtime/aux/mcp-auth`
     - `~/.jules` → `Workspace/limen/.agent-runtime/aux/jules`
     - `~/bound` → `Workspace/limen/.agent-runtime/shared/bound`
- **Output**: `domus-home-guard --check` violations on agent directories drop to `0`.

---

## 5. Premortem (Rule #24 Triadic Review — Updated for v2)

- **Sympathetic**: Every mutation is now backed by live byte/SQLite measurements already gathered in this session (`~/.claude.json` byte-match confirmed; `~/.local/share/codex` 2,688-thread disjoint set identified; `chezmoi status` refreshed against `domus-genoma` `94ed4c76`).
- **Adversarial**:
  1. *Risk*: Archiving all 3.29 GB of `~/.local/share/codex` while free disk is 17.9 GB could trip `limen.runtime_pool.v1` reserve thresholds during copy.
     *Mitigation*: Check `domus-agent-runtime quota --json` before staging; copy SQLite databases with `cp -Rc` (APFS clonefile, which consumes **zero additional physical blocks** on the same APFS volume!) into `$LIMEN_CUSTODY_STAGING_ROOT`, then compute SHA-256 manifests.
  2. *Risk*: A doorway symlink breaks a tool that checks `lstat()` on its `$HOME` dot-dir.
     *Mitigation*: Test each doorway one vendor at a time against the §6 Consumer Matrix and keep the pre-link state + JSON receipt for instant one-command rollback.
  3. *Risk*: Modifying `domus-genoma` conflicts with the dirty `.serena/project.yml` in the main checkout.
     *Mitigation*: Never mutate the main checkout; use a linked worktree after verifying `host-work-admission.py status --no-probe`.
- **Orthogonal**:
  - *Assumption*: Copying 3.29 GB on APFS requires 3.29 GB of new disk blocks.
  - *Correction*: Because `~/.local/share/codex` and `/Users/4jp/Workspace/limen/.limen-private/custody-staging` reside on the same APFS volume (`/dev/disk3s5`), `cp -Rc` (clonefile) creates an independent, immutable copy-on-write custody tree in milliseconds using **0 bytes of additional disk space**, which can then be checksummed and verified before any retirement!

---

## 6. Explicit 8-Consumer Verification Matrix

Every phase that touches a consumer's config, skills, or doorway must verify all four columns for that consumer before marking the phase complete:

| Consumer | 1. Instruction Discovery | 2. Skill Discovery & Invocation | 3. State / History Continuity | 4. One-Command Rollback Tested |
| :--- | :--- | :--- | :--- | :--- |
| **Claude Code (`claude`)** | Loads `$CLAUDE_CONFIG_DIR/CLAUDE.md` + `~/AGENTS.md` | Lists shared skills; invokes `v-preflight` | Reads/writes `$CLAUDE_CONFIG_DIR/.claude.json` & `projects/` | Restore `settings.json` / `.claude.json` receipt |
| **Codex (`codex`)** | Loads `$CODEX_HOME/AGENTS.md` + `~/AGENTS.md` | Lists `$CODEX_HOME/skills`; `codex doctor --summary` = 24 ok | Reads `$CODEX_HOME/state_5.sqlite` & `history.jsonl` | Restore `config.toml` / custody clone |
| **Gemini CLI (`gemini`)** | Loads `$GEMINI_CLI_HOME/.gemini/GEMINI.md` | Lists `$GEMINI_CLI_HOME/.gemini/skills` | Reads `$GEMINI_CLI_HOME/.gemini/history/` | Restore `gemini/home` backup |
| **Antigravity (`agy` / IDE)** | Loads `<RULE[user_global]>` (`config/AGENTS.md`) | Loads `skills.json` (`~/.agents/skills`) | Reads `antigravity-cli/brain/` & `conversation_summaries.db` | Restore `~/.gemini` symlink target receipt |
| **OpenCode (`opencode`)** | Loads `~/AGENTS.md` & `~/.config/opencode/AGENTS.md` | Lists `~/.config/opencode/skills` | Reads `$LIMEN_AGENT_RUNTIME_ROOT/opencode/data/opencode/opencode.db` | Restore `opencode.json` seed + doorway receipt |
| **GitHub Copilot (`copilot`)** | Loads `~/.copilot/instructions/` & `copilot-mcp.json` | Connects MCP via `~/.local/libexec/domus/shims/copilot` | Preserves `~/.copilot` & `~/.github-copilot-cli` state | `domus-home-guard` doorway rollback receipt |
| **Cursor (`cursor`)** | Loads `~/.config/ai-instructions/cursor-rules/core.mdc` | Reads `<repo>/.agents/skills` | Preserves `~/.cursor/extensions` & `ai-tracking` | `domus-home-guard` doorway rollback receipt |
| **Claude Desktop** | Loads MCP config (`claude_desktop_config.json`) | Connects enabled MCP servers without truncation | Preserves `Library/Application Support/Claude/vm_bundles` | Restore `claude_desktop_config.json.bak` |

---

## 7. Concrete Rollback Receipts Contract

Every symlink change or file quarantine in Phases 1–4 must write a JSON receipt to `/Users/4jp/.local/state/domus/home-residue/<action>-receipt-YYYYMMDD.json` containing:
```json
{
  "action": "relink-or-quarantine",
  "path": "/Users/4jp/.claude.json",
  "previous_kind": "file",
  "previous_target_or_backup": "/Users/4jp/.local/state/domus/home-residue/.claude.json.pre-relink-20261017",
  "sha256": "<64-hex>",
  "recorded_at": "2026-10-17T16:10:00Z",
  "undo_command": "ln -f /Users/4jp/.local/state/domus/home-residue/.claude.json.pre-relink-20261017 /Users/4jp/.claude.json"
}
```

---

## 8. Superseded provisions (appended 2026-10-18; original text above is unchanged)

Plans are append-only, so §5 and §7 stay as written. Where they conflict with this block, this block governs.
Evidence and dispositions: `docs/plans/2026-10-18-agent-surface-reconciliation-v3.md` § Corrections to v2.

1. **§5 (mitigation 1 and the Orthogonal correction): an APFS clone is not custody.** The text above calls a
   `cp -Rc` clone "independent, immutable" and "zero additional blocks". A clone is a writable copy on the *same
   volume*. It is neither immutable nor independent, and while it exists, deleting the source frees no blocks, so
   "stage then retire" does not relieve quota. Custody requires a second device plus a checksum manifest; set the
   staged tree read-only; claim reclaimed space only once the source is gone *and* a second copy exists elsewhere.
2. **§7 (receipt contract): `undo_command` must never delete the destination first.** The live receipt
   `~/.local/state/domus/home-residue/codex-custody-receipt-20261017.json` records the same
   `rm -rf <dest> && cp -Rc <backup>/. <dest>` in all three of `one_command_undo`, `undo_command` and `rollback_cmd`.
   Replayed after the destination has accumulated new history, that destroys the history, and a failed copy leaves
   nothing. The receipt lives outside git and was not edited. Corrected rollback for that receipt (rename aside, copy
   back, verify, delete nothing):

   ```sh
   D=/Users/4jp/.local/share/codex
   B=/Users/4jp/Workspace/limen/.limen-private/custody-staging/codex-legacy-share-20261017T171401Z
   test ! -e "$D" || mv "$D" "$D.pre-rollback-$(date -u +%Y%m%dT%H%M%SZ)"
   cp -Rc "$B" "$D"
   (cd "$D" && shasum -a 256 -c --quiet manifest.sha256)
   ```

   As of 2026-10-18 `$D` does not exist (the share was retired), so the `mv` is a no-op and the sequence restores from
   custody. Any future receipt must carry an `undo_command` of this rename-aside shape, plus a `verify_command`.
3. **Census claims (Phase 1B, §1): not exhaustive.** A depth-bounded `find` cannot establish an inventory. The ledger
   (v3 item 7) must record its method, depth, prune list, every scan error, and a deduplicated physical-directory count.
