# Plan v3: reconcile agent-surface containment (Claude lens) — status, delta, owners

Issue: #2848
PR: (pending)

- **Date**: 2026-10-18
- **Supersedes nothing.** Reconciles `docs/plans/2026-10-17-unify-contain-agent-surfaces-v2.md` (limen) and OpenCode's
  PR #502 plan (`domus-genoma-private`, `.claude/plans/2026-10-17-agent-surface-unification.md`) against **live disk**.
- **Inputs (2026-10-18)**: four provider sessions answered the same four questions — Claude (this plan's first
  draft), Codex (with an adversarial review of v2), Antigravity/`agy`, and OpenCode (PR #502). Each claim below was
  re-read from disk before use; claims taken from a provider's own report are marked *(reported)*.
- `PR: (pending)` is the PR that will *implement* the remaining items, not the PR that ships this document.

## Context

The request repeats, for Claude, what OpenCode answered earlier today: where does the agent exist on disk, what
customizes it, does it read `.agent-runtime`, and how do we contain every provider's files. Two plans already own the
architecture (4-ring model, doorways, custody-first, 8-consumer matrix). A third architecture would fork parallel
substrate. The deliverable is: **what landed, what remains, who owns it.**

## Answers (evidence from the 2026-10-18 session)

### Does Claude get context from `.agent-runtime`? **Yes, by design** (opposite of OpenCode)
`$CLAUDE_CONFIG_DIR` = `.agent-runtime/claude/`. The session loaded `claude/CLAUDE.md` (the rendered adapter, imports
`~/AGENTS.md`) and `claude/projects/-Users-4jp-Workspace-limen/memory/MEMORY.md` from there, plus the repo's
`CLAUDE.md`/`AGENTS.md`. OpenCode instead fell through to `~/AGENTS.md` for want of a shim; that gap is closed
(`~/.config/opencode/AGENTS.md` is live; healthcheck 28 → 42 ok). `~/.claude` is only a doorway to the retired
`claude/legacy-home`; live config does not read it.

### Where Claude exists locally, by ring
| Ring | Path | Size | Contained? |
|---|---|---|---|
| 1 live runtime | `.agent-runtime/claude/` (settings, CLAUDE.md, agents, skills, plugins, projects, memory, history) | 2.4 GB (projects 1.9 GB) | Yes — `$CLAUDE_CONFIG_DIR` |
| 1 retired layer | `claude/legacy-home/` ← `~/.claude`; `legacy-home.json` ← `~/.claude.json` | 331 MB (plans 112, file-history 141) | Doorways in place; retirement gated (Step 8) |
| 2 OS-fixed | `~/Library/Application Support/Claude` (Desktop) | **12 GB; `vm_bundles` 11 GB** | Never symlinked (TCC/codesign); `domus-agent-maintain` |
| 2 OS-fixed | `~/.local/share/claude` (native installer: `versions/`, `ClaudeCode.app`) | 495 MB | Fixed by native install; never move |
| 3 per-repo | `limen/.claude/` (settings, 3 agents, 8 skills, plans, worktrees) + ~190 `.claude/.codex/.gemini` hits across worktrees | — | Tracked project surface; die with their worktree |
| shared | `~/AGENTS.md`, `~/.config/{ai-context,ai-instructions,ai-skills,ai-tools,agents}`, `~/.agents/{skills,teamwork}` | — | Ring 0 liturgy/catalog, chezmoi-managed |

### Claude customizations (two layers)
- **User layer** (`claude/settings.json`, chezmoi-rendered): defaultMode `auto`, model `sonnet`; 7 hooks over 4 events
  (SessionStart ×2, PreToolUse guard-dispatch ×3 matchers, PostToolUse `domus-agent-hook`, SessionEnd closeout);
  16 enabled plugins; 6 env keys (names only); statusline script; 3 agents (builder/scanner/verifier); 4 skill symlinks;
  `CLAUDE.md` adapter.
- **Project layer** (`limen/.claude/`): defaultMode **`plan`** (the repo's entry binding), 55 allow rules, 4 hook events,
  agents `scan/synth/verify`, 8 repo skills, `settings.local.json`.
- Precedence: project overrides user for `defaultMode` — which is why sessions here open in plan.

## Cross-provider matrix (Q3: does the agent read `.agent-runtime`?)

| Provider | Instruction path actually loaded | Reads `.agent-runtime`? | Evidence |
|---|---|---|---|
| Claude Code | `claude/CLAUDE.md` (imports `~/AGENTS.md`) + `claude/projects/*/memory` | **Yes** — config, memory, history | this session's loaded context |
| Codex | `codex/AGENTS.md` + memory summary + skill catalog backed by `codex/` | **Yes** — `$CODEX_HOME` *is* the runtime dir; `~/.codex` points straight at it | *(reported)*; `~/.codex` symlink read from `ls -la ~` |
| Gemini CLI | `gemini/home/.gemini/GEMINI.md` | Yes | manifest row; healthcheck `chezmoi-managed (live)` |
| Antigravity | `<RULE[user_global]>` from `gemini/legacy-home/config/AGENTS.md`, `mcp_config.json`, `skills.json` via `~/.gemini` | **Partly** — reaches only the `gemini/legacy-home` subtree; its `skills.json` points at `~/.agents/skills`, so the 28 skills in `.agent-runtime/.agents/skills` are invisible to it | *(reported)* |
| OpenCode | `~/.config/opencode/AGENTS.md` (now live) → `~/AGENTS.md` | **State only** — `opencode/{data,state,cache}`; instructions live under `~/.config` because OpenCode has no config-relocation variable | healthcheck line `~/.config/opencode/AGENTS.md … chezmoi-managed (live)`; launcher source |

Result: four of five agents resolve instructions through `.agent-runtime`; OpenCode is the structural exception, and
its exception is deliberate, not drift.

## Corrections to v2 (adversarial review of the Codex session, each verified)

v2 is merged (#2925), so these provisions are live on `main` and must be amended, not merely noted.

| # | v2 provision | Finding | Disposition |
|---|---|---|---|
| 1 | §5 "APFS clone … immutable … 0 bytes" | A clone is a writable same-volume copy, not immutable and not independent storage custody. It also reclaims nothing: while the clone exists, deleting the source frees no blocks, so "stage then retire" does not relieve quota. | **Accept.** Custody needs a second device plus a checksum manifest; set the staged tree read-only; do not claim reclaimed space until the source is gone *and* a second copy exists elsewhere. |
| 2 | §7 receipt `undo_command` (`rm -rf <dest> && cp -Rc <backup> <dest>`) | Confirmed in `codex-custody-receipt-20261017.json`: all three recorded rollbacks delete the destination first. A replay after the destination accumulates new history destroys it, and a failed copy leaves nothing. | **Accept.** Rollback = rename destination aside (`.pre-rollback-<ts>`), copy back, verify, never delete. Rewrite the receipt contract and regenerate the three commands. |
| 3 | "census" claims | Depth-bounded `find` cannot establish an exhaustive inventory; wildcard groups stand in for enumeration. | **Accept.** See item 7: ledger with method, depth, prune list, scan errors, and deduplicated physical count. |
| 4 | Codex session blocker narrative | A scope denial and a separate admission reading were reported as one cause. | **Accept as process rule** (execution rails): name the denying layer, don't infer it from an unrelated status. |
| 5 | Codex step 5 "one explicit root cutover" to `~/.local/state/domus/agent-runtime` | The code default (`domus-agent-runtime.py:115-129`) is for *new* installs; it raises unless the legacy root is explicitly selected. Nothing shows a defect on this host that moving the root would fix. | **Reject for now.** No cutover. Reopen only if a measured containment defect needs it, with the references and consumers counted first. |
| 6 | `agy` session: "delete duplicate `~/.gemini/bin/agy` (181 MB) and the 49 MB temp tarball" | Already rejected in v2 §0 #4 (the Antigravity updater manages that path). The `agy` census also reported v1.4.0 while the banner showed 1.4.2. | **Reject deletion; keep quarantine-first.** Census must read versions live, not copy them from memory. |
| 7 | `agy` plan written to `.agent-runtime/claude/plans/` | Gitignored, so the plan was never durable — the `s-02-plan` defect v2 Phase 3 already owns. | **Confirmed; no new work.** |

## Reconciliation of v2 + #502 against live state

| Item | Evidence | Status |
|---|---|---|
| v2 1A `~/.claude.json` relink | `~/.claude.json` is a symlink → `legacy-home.json` | **landed** |
| v2 1B `~/.local/share/codex` custody | no `codex` in `~/.local/share`; `domus-agent-runtime check` ok, 0 unauthorized legacy roots | **landed** |
| v2 4 eleven home doorways | all present as symlinks in `ls -la ~` | **landed** |
| #502 defect 2 OpenCode shim | `~/.config/opencode/AGENTS.md` live; healthcheck 42 ok / 0 fail | **landed** |
| v2 2 Antigravity cutover | `antigravity/` staged; `~/.gemini` still → `legacy-home` | **gated** (rollout Step 8) — no change proposed |
| v2 plan itself | PR #2925 MERGED 2026-10-17T18:32Z (carries the unsafe provisions above) | **landed, needs amendment** |
| #502 OpenCode plan | PR #502 MERGED 2026-10-18T00:48Z; its Phase A (apply pending surfaces) is visible in the 28 → 42 healthcheck | **landed**; B–E open |
| v2 3 skills reconcile | ≥3 roots: `~/.agents/skills` (30), `.agent-runtime/.agents/skills` (31), `shared/skills-catalog` (69 + registry) | **open** |
| `legacy-home` retirement | 331 MB still behind doorways | **gated** (Step 8) — observe only |
| home-guard | `FAIL`, 1 violation: `.grokbot` route blocked, destination exists | **open** |

Caveat: "landed" rests on filesystem reads, not receipts; closeout re-proves each with its predicate.

## Remaining work and execution owner (one owner per item)

1. **`.grokbot` — domus-genoma PR (`home-surface.yaml`).** Live read corrects the diagnosis: `~/.grokbot` is an *active*
   app (daemon log and supervisor written minutes before the read), not residue. The declared "route to
   `home-residue/.grokbot`" already ran once (residue copy dated Oct 17 13:09) and the app recreated the dir. Fix:
   reclassify from `route_pending` to an `application` `preserve-and-link` doorway → `.agent-runtime/aux/grokbot`,
   guarded by `_exact_process_active()`; reconcile the two trees by inspect-then-merge (never delete, never overwrite
   the residue copy). Linking needs the daemon stopped — flag that sequencing constraint; do not kill it.
   **Status (2026-10-18, later): domus PR #506 MERGED (`dfd82054` on `origin/main`); live checkout fast-forwarded; the
   deployed manifest is NOT yet updated and the route is NOT applied.** Two corrections to the
   text above, both from live reads: (a) no grokbot process was running at implementation time and the directory was
   last written hours earlier, so the "daemon must be stopped" constraint was moot then (the guard's active-CWD check
   still enforces it at apply time); (b) the declared `move` was not merely redundant, it was *permanently blocked*
   (`destination already exists`), which `domus-home-guard --check` showed on `main`. The residue copy was **not**
   merged into the live tree: it holds a stale credential and connection file the daemon regenerates, so it stays as
   custody. **Apply is blocked on a denial, not on a defect:** the auto-mode classifier denied `chezmoi apply
   ~/.config/domus/home-surface.yaml` once, with no reason given. `chezmoi diff` for that target shows exactly the
   `.grokbot` entry and route and nothing else. Not retried and not routed around (the guard apply would be the same
   change to `$HOME`). Operator sequence: `chezmoi apply ~/.config/domus/home-surface.yaml`, then
   `domus-home-guard --check --json` (read `plan_hash`), then `domus-home-guard --apply --plan-hash <hash>`, then
   `domus-home-guard --check` (the three `.grokbot` violations clear; `visual_dashboard.html` is pre-existing).
2. **Skills (v2 Phase 3) — domus-genoma PR.** Content-hash inventory across the three roots; register survivors in
   `skills-registry.json`; no pruning before Step 8. Close the cross-provider leak seen from Claude's side: two of four
   `claude/skills/*` links resolve into Claude-named paths (`distributions/claude/…`, `limen/.claude/skills/vendor-insights`).
   Canonical home = `ai-skills/` with per-provider fan-out links, never one provider's namespace.
   **Status (2026-10-18, later): premise corrected by measurement; delivered as domus PR #507 (MERGED, `9e3893a5`) +
   issue #508.** Measured with the new read-only `domus-skills-census`: (a) `~/.agents/skills` and runtime
   `.agents/skills` share **zero** names, so they are complementary sets, not duplicates, and there is nothing to
   dedupe or crown canonical; (b) the "cross-provider leak" is overstated: `distributions/claude` and
   `distributions/codex` are complete copies inside the catalog, and the three Codex links into the claude flavor are
   byte-identical (a naming/coupling concern, not a content leak); only `vendor-insights` crosses into the limen repo,
   and #456 documents that as deliberate; (c) the real defect is `closeout` having two contents: the Domus copy (#505,
   Oct 18) is newer than the Oct 16 catalog copy that Claude, Codex and OpenCode load, filed as #508. The connector,
   allowlist and consolidation work is owned by five open PRs (#435, #456, #436, #443, #414), so no competing skills
   branch was cut. Registry registration and pruning stay gated to Step 8.
3. **`vm_bundles` 11 GB — limen (owner + predicate).** Same class as OpenCode's `opencode.db`: large, monotonic, no
   named prune owner. File `domus-agent-maintain` as owner with a bounded prune predicate; do **not** symlink (Ring 2).
   **Status (2026-10-18, later): premise wrong for both stores; the real defect is a readers-point-at-the-wrong-file
   bug, fixed in limen PR #3029 (open, HOLD: 9 required checks running, 0 failing).** `vm_bundles` already has an owner
   and policy: `home-surface.yaml` `application_objects` names owner `Claude Desktop VM`, adapter
   `domus-claude-vm-lifecycle` and a retirement policy ("retain until compressed-base identity and native cold-start
   reconstruction are verified"), so no action. `opencode.db` already has an owner too
   (`aw-opencode-db-corpus-intake-0709`, gate "never delete outright", in `substrate-storage-pressure.py`) and a
   preserver (`opencode-db-corpus-intake.py`), but all of them read `~/.local/share/opencode/opencode.db`, a symlink to
   the frozen 8 MB `legacy-share` copy. The live store is `.agent-runtime/opencode/data/opencode/opencode.db`
   (3.07 GB, written daily). Eight readers shared that stale path; #3029 gives them one resolver. **Open, owner-routed,
   not done here:** the intake owner's log was last written Jul 10 and the archive holds two July runs, so the live
   database has not been preserved since July. Running it copies 3 GB to `/Volumes/Archive4T` under swap pressure
   (host admission denied heavy work), so it waits for a calm host: `python3 scripts/opencode-db-corpus-intake.py`
   (never deletes the source). Whether the frozen 8 MB copy is a subset of the live store is unverified.
4. **`legacy-home` — no action** until Step 8; record its 112 MB `plans/` and 141 MB `file-history` as
   custody-before-retire inputs (v2 §4 pattern).
5. **Loose files in the runtime root — limen.** `.agent-runtime/` top level holds four OpenCode session exports
   (~1.8 MB), `correction_drafts/`, `scratch/`, `.recode/`. Quota-bound vendor state is the wrong home for transcripts;
   route to `$LIMEN_CUSTODY_STAGING_ROOT` or the transcript corpus with receipts. (The "contain all *files*" half that
   v2 did not cover.)
   **Status (2026-10-18, later): the four transcripts moved; the other three items have owners and were left alone.**
   Moved to `$LIMEN_CUSTODY_STAGING_ROOT/runtime-root-loose-files-20261018/` (mode 0700) by same-volume rename: 4 files,
   1,796,641 bytes, sha256 verified before and after, private `receipt.json` with `mv -n` undo commands (rename, so
   nothing deleted; originals' mtimes preserved). Left: `.recode/changes.db` is **1.9 GB**, not the small item the
   plan implied, and domus `docs/runtime-maintenance-lifecycle.md` already lists "shared `.recode`" under *Other
   storage owners* (classify before moving anything); `correction_drafts/` (2 files, Aug 15) are named for people, so
   they are person-records: not read, not moved; `scratch/` (2 files, Oct 17) are another lane's PR-body drafts.
6. **Amend v2 — limen docs PR.** Apply corrections 1–2 above to `2026-10-17-unify-contain-agent-surfaces-v2.md` §5 and
   §7 (append-only: plans are never overwritten, so add a dated "Superseded provisions" block that points here), and
   regenerate the three Codex receipt rollbacks with the rename-aside form. The receipts live under
   `~/.local/state/domus/home-residue/`, outside git — record the corrected commands in a tracked receipt note.
   **Status (2026-10-18, later): done in this PR.** v2 §8 "Superseded provisions" is appended (the original text is
   untouched). The live receipt was confirmed to hold the same destructive `rm -rf … && cp -Rc` in all three of
   `one_command_undo`, `undo_command` and `rollback_cmd`; it lives outside git and was not edited. The corrected
   rename-aside sequence (with a `shasum -c` verify) is in v2 §8, and the receipt contract now requires it.
7. **Census ledger — domus-genoma (extends #502 Phase B).** One script emits a tracked ledger: for every provider, each
   physical location with `realpath`, owner, consumers, size, and role; aliases listed separately from copies; scan
   method, depth, prune list and every scan error recorded; a deduplicated physical-directory count. Seed it with the
   locations the Codex session reported and this plan verified: `/Applications/ChatGPT.app/Contents/Resources/codex-cli`,
   `~/Library/{Application Support,Caches}/Codex`, `~/.cache/codex-runtimes`, `~/Documents/Codex`,
   `~/Workspace/session-meta/codex`, `~/.config/goose/chatgpt_codex`,
   `/Library/Application Support/CodexComputerUseAuthorizationPlugin`. Protected system caches are recorded as
   "not scanned, reason", never silently omitted.
   **Status (2026-10-18, later): domus PR #509 MERGED (read-only `domus-agent-location-ledger` + committed baseline
   `docs/receipts/2026-10-18-agent-location-ledger.json`).** It measures 42 declared locations (40 present, 2 absent,
   0 dangling; 39 unique realpaths, 29 non-nested roots, about 44 GiB), lists aliases apart from copies, sums size over
   non-nested roots only, records method and limits, and exits 1 only on a scan error. Its depth-1 discovery found **36
   provider-looking locations no seed row covered** (for example `com.openai.codex` under Application Support, Caches and
   Logs, `~/.cache/opencode`, `~/.cache/claude`, the Antigravity IDE support dir), which is the exact gap the Codex
   census had. They are listed, not classified: promoting one to a seed row is an owner decision.
8. **Antigravity skills visibility — domus-genoma (inside item 2).** `skills.json` targets `~/.agents/skills`, so the 28
   skills in `.agent-runtime/.agents/skills` never reach it; the content-hash reconciliation decides which root is
   canonical before any `skills.json` edit. **Superseded premise (2026-10-18, later):** the census shows the two roots
   are disjoint, so no root is "canonical" over the other; the open question is only which consumers should read which
   root, which is still gated on the skills lane (#435/#456/#436) and Step 8, not on a hash reconciliation.
9. **No root cutover** (correction 5): recorded as a decision, not left implicit.
10. **Out of scope:** per-repo `.claude/` dirs and worktree copies (v2 disposition #8, separate opt-in track),
   Library/Application Support moves, `~/.agents/teamwork`, and #502's human gate (GitHub/Serena/Jupyter MCP vs `ianva`
   for OpenCode) — OpenCode's gate, already filed; not re-raised.

## Reconciliation of the two OpenCode sessions (vendor-insights, AGENTS.md rewrite)

Both pasted sessions closed with "pending" states. Each was re-read against `origin/main` and GitHub on 2026-10-18;
three of the four pending claims had already resolved, so nothing from them becomes a new work item.

| Pasted claim | Live state | Disposition |
|---|---|---|
| PR #2949 (vendor-insights store resolution) is open, hold for review | `MERGED` 2026-10-18T01:42Z; `insight-cross-vendor-ingest.py` on main resolves the per-workspace `.agent-runtime/*/opencode.db` roots via `extra_root_globs` | Landed. Accept the finding (moved stores read as false zero); no action |
| `docs/agent-docs-repo-map-fixes` is unpushed (custody copy only) | Pushed at 3b346f6; PR #2976 closed unmerged *by design*, superseded by #2985, which carries 3b346f6 plus the six Codex-finding fixes; #2985 is on main | Landed. The custody copy is redundant but kept (never deleted) |
| `.venv` paths in instruction files break `check-agent-docs.py` in fresh clones | `AGENTS.md` on main routes through `scripts/lib/gate-python.sh` and says never hardcode a `.venv` path | Landed. Accept; no action |
| `stash@{0}` is an unowned vendor-insights WIP | The stash is labelled `pre-D3 realign 2026-10-17: shared-checkout WIP` and names its preservation copy in the private custody repo | Owned and preserved, not unowned. Do not pop, apply, or drop it from this plan; its owner closes it |
| Guard wiring is uneven across lanes | **True at the repo level.** `.claude/settings.json` binds three guards (pytest-scope, no-hand-poll, worktree-commit); `.codex/hooks.json` binds only `no-hand-poll`, via `codex-hook-runner.sh`. `AGENTS.md` on main already documents this. The outbound-preflight guard is the exception: wired in *no* lane (uniformly unarmed), with a standing arming runbook (`docs/runbooks/outbound-preflight-arming.md`) | Accept for the three wired guards (documented, no action); the outbound guard is a filed human lever, not re-raised here. An earlier draft of this row rejected the claim after checking only the outbound guard in runtime configs, which could not answer it |

Two durable lessons, recorded here because no other surface owns them:
1. A pasted session's "pending" list is a snapshot. In this case it was hours stale on every item, so re-verify against
   `origin/main` and `gh` before turning any of it into work. Ancestry alone misleads on squash repos; the PR #2976
   closure shows a closed-unmerged PR can still be fully landed through its successor.
2. **Item 3 gets a measured size:** the live `opencode.db` is 3.07 GB (the legacy-share copy is 8 MB), modified the same
   day. An earlier draft of this lesson called that a "no-named-prune-owner" case and proposed adding it to item 3's
   scope. **Superseded:** item 3's status above shows `opencode.db` already has an owner and a preserver; the real defect
   was that they read the frozen legacy file (fixed in #3029). Growth rate is still not measured.

## Execution rails
- Writer lease first: `python3 scripts/host-work-admission.py status --no-probe` should report `allowed: true`. It
  reported `false` (swap-fraction, 14 Codex leases) on 2026-10-18; this docs-only worktree was created under an explicit
  operator override. Implementation items 1–5 do **not** inherit that override.
- Items 1–2 → one `domus-genoma` worktree PR each; items 3, 5 → one limen docs/predicate PR; one commit per concern.
- Every move writes a rollback receipt under `~/.local/state/domus/home-residue/` (v2 §7 contract).
- Name the denying layer. Drafting this plan met three separate layers — the background-isolation guard (rejected
  writes outside a worktree), the writer-lease reading (`allowed:false`, advisory input to the worktree decision, not a
  denial), and the auto-mode classifier (rejected one file write). Do not attribute one layer's outcome to another.
- Do not dump `env`; the guard denies it. The runtime root is known from `domus-agent-runtime check`.

## Verification (predicates, not prose)
- `domus-home-guard --check` exits 0 (read its own exit code, no pipe).
- `domus-agent-runtime check` stays `ok`, 0 unauthorized legacy roots.
- `agent-surface-healthcheck` stays ≥ 42 ok / 0 fail. Per #502 defect 4 it cannot see directories/globs/symlink
  targets, so green is not proof for skills — add a skills-root census check as part of item 2.
- `domus-skills-census` (domus PR #507) exits 0. **Currently exits 1 on this host**: one same-name collision,
  `closeout`, owned by issue #508. That is the predicate working, not a regression; do not wire it into a gate until
  #508 resolves.
- `domus-home-guard --check` against the #506 manifest shows `.grokbot` as a non-blocked `preserve-and-link` (on `main`
  it is a blocked `move`). It stays non-zero until the route is applied; `visual_dashboard.html` is a pre-existing,
  unrelated `undeclared_home_entry`.
- `scripts/check-session-phase.py` exits 0 for this plan (Issue + PR lines present).
- Re-run the 8-consumer matrix (v2 §6) rows for Claude Code, Claude Desktop, and OpenCode after items 1–2.
