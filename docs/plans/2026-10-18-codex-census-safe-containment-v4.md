# Codex census and safe agent containment handoff — revision 4

Issue: #2848
PR: publication is recorded in the companion session-closeout.json

Date: 2026-10-18. Owner: [Limen #2848](https://github.com/4444J99/limen/issues/2848).
This supplements [the existing v3 owner PR](https://github.com/4444J99/limen/pull/3026)
and [Domus Phase B](https://github.com/4444J99/domus-genoma-private/pull/502).
It supersedes v2's recovery claims and destructive rollback contract, not its entire architecture.
No runtime root migration, native state retirement, provider restart, or live rollback is performed here.

## Disposition of the six findings

1. **Accepted.** APFS clones can diverge after writes and share backing storage. They do not
   establish immutability, independent failure-domain custody, or literal zero storage cost.
   Apple's [current APFS documentation](https://developer.apple.com/documentation/foundation/about-apple-file-system)
   describes clone behavior. Same-volume staging is useful only as staging. Read-only permissions
   are not immutable storage. Custody acceptance requires an independent replica and verified
   restoration through the existing preservation owner; no native data is deleted in this handoff.
2. **Accepted.** Depth-limited searches are discovery samples. The supplied scanner uses no depth
   limit or name-based subtree pruning, retains every named match and alias, deduplicates by
   device/inode, records every failed metadata operation, and returns 2 when coverage is incomplete.
3. **Accepted.** This revision, runnable tools, fixture checks, coverage result, and publication
   evidence belong in this Git branch/PR. The prior rejected scratch draft is not evidence.
4. **Accepted.** Historical workspace-scope-unavailable and separate swap-fraction are
   distinct observations. This session separately observed shared-checkout-write for structured
   workdir/file calls and successful explicit git -C / documented cd scope. No causal link
   from swap pressure to those scope denials is established.
5. **Accepted.** Retain the explicitly selected Workspace/limen/.agent-runtime root.
   Domus runtime_root() accepts that explicit selection; its fresh-install default is not a
   migration recommendation. Root migration requires a measured defect, counted references,
   all affected consumers, and separate restore/cutover acceptance.
6. **Accepted.** The mapping, source edits, ordering, rollback, and observable acceptance below
   replace the previous six-step sketch. Remaining execution is owned by the existing issues/PRs.

## Census contract and retained evidence

The exact private ledgers enumerate paths; the public coverage receipt contains counts only.
The predicate is **case-insensitive basename contains codex**, plus separately recorded aliases
whose path or link target contains codex. A match may be historical source, a worktree, an installer,
a cache, a native store, or an unrelated name; the count is not the count of active installations.
Known consumers with other names are covered by the provider mapping below.

Default roots: Applications, Library, opt, usr/local, the complete Workspace and home, private,
System, Volumes, Users, and finally /. Overlapping views are deduplicated by (st_dev, st_ino).
No maxdepth and no .git/node_modules exclusions. Mount metadata is retained. Nonlocal/virtual mounts
are excluded explicitly; directory symlinks are recorded without traversal, with target identity
when resolvable. Physical mount traversal reaches local targets independently of alias names.
Dataless cloud directories, access errors, disappearing paths, and two-second metadata timeouts
are retained as coverage errors. The five-minute run deadline produces exact pending paths.
A live traversal is not an atomic snapshot: concurrent changes remain a limitation.

Reproduce from this checkout (choose a **new** output directory; never overwrite evidence):

~~~sh
python3 docs/continuations/agent-surface-containment-20261018/inventory.py scan --output .limen-private/census-next --seconds 300
python3 docs/continuations/agent-surface-containment-20261018/inventory.py verify --output .limen-private/census-next
python3 docs/continuations/agent-surface-containment-20261018/check-tools.py
~~~

Each command is a separate invocation. Scan/verify exit 0 means complete coverage for the declared
roots; exit 2 preserves measured gaps. Fixture-test success is a tool check, not census completion.
The initial interrupted scan is retained separately; its failure is not silently replaced.

## Current-to-target mapping

R below means the existing explicitly selected runtime root. Source paths are relative to
the **private Domus source repository**, not Limen. Current doorway links were read on this host.
A target of "retain" means no new move is justified.

| Provider/surface | Current location / consumer | Target and concrete source owner/edit | Acceptance before change is complete |
|---|---|---|---|
| Codex | ~/.codex -> R/codex; app/CLI state, config, hooks, memory, skills | Retain. Config atom edits in Workspace/limen/private_dot_agent-runtime/private_codex/modify_private_config.toml.tmpl; ownership keys in .chezmoidata/config-ownership.json; adapter private_AGENTS.md.tmpl; hooks modify_private_hooks.json.tmpl | TOML parse; owner-managed diff only; app-owned blocks byte-identical; second render unchanged; native session instruction, skill and history readback |
| Claude Code | launcher selects R/claude; ~/.claude -> R/claude/legacy-home; legacy JSON doorway | Retain both. Source Workspace/limen/private_dot_agent-runtime/private_claude/; never assume legacy alias is the active config | Native instructions/settings readback, known skill invocation, old and new history present; unchanged legacy custody |
| Gemini CLI | launcher sets GEMINI_CLI_HOME=R/gemini/home, native .gemini beneath it | Retain. Source Workspace/limen/private_dot_agent-runtime/private_gemini/private_home/dot_gemini/ | Adapter and skills discovered in fresh native session; history continuity |
| Antigravity | ~/.gemini -> R/gemini/legacy-home; ~/.antigravity-ide -> R/antigravity/dot-antigravity-ide | Preserve updater-owned bin and histories. Sources private_gemini/legacy-home/config/{AGENTS.md,skills.json}.tmpl, dot_local/libexec/domus-agent-runtime.py, dot_config/domus/home-surface.yaml; cutover still belongs to rollout Step 8 | Resolve every doorway; skills visible; updater completes a cycle; known conversations reopen; Step 8 predicate and independent restore proof |
| OpenCode | app-owned ~/.config/opencode/opencode.jsonc; shared adapter there; runtime data/state/cache under R/opencode | Retain split. dot_config/opencode/AGENTS.md.tmpl, instruction-surface manifest and launcher. Do not overwrite app JSONC with historical seed JSON | Instructions and intended MCP discovery; known session readback; no unknown configuration keys dropped |
| GitHub Copilot | ~/.copilot -> R/copilot/dot-copilot; ~/.github-copilot-cli -> R/copilot/dot-github-copilot-cli | Retain doorways. dot_copilot/private_instructions/shared-context.instructions.md.tmpl and dot_config/domus/home-surface.yaml | Both consumers resolve links, read instructions and retain histories independently |
| Cursor | ~/.cursor -> R/cursor/dot-cursor; project rules and skills remain project-owned | Retain doorway; source home-surface declaration and existing Cursor instruction source named by manifest | Extensions, project rules, skill discovery and history readback; preserve app OS storage |
| Claude Desktop / ChatGPT / Codex apps | OS-owned Application Support, Caches, app bundles and authorization plugin | Retain OS locations. Classify and measure through provider lifecycle adapters; no blanket symlink of Library or app bundles | Native launch and known-state readback; any cleanup requires its own bounded lifecycle and custody predicate |
| Shared skills | ~/.agents/skills, R/.agents/skills, installed skill catalog and provider projections | Existing skills PRs #435/#436/#443/#456 and #508 own reconciliation; do not assume same-name or differently named roots are duplicates | Content/provenance census, declared consumer matrix, each intended skill visible; no pruning to make a check pass |
| Auxiliary agents | declared home doorways; active Grokbot exception | Existing Domus #506 owns Grokbot; home-surface source owns other routes. Preserve live and residue copies separately | Fresh home-guard result, exact process guard, both histories retained, no destination collision |

These are configuration/location facts, not claims that every native acceptance row was exercised.
All source-owned changes use an isolated Domus worktree and the existing manifest, never edits to
deployed configs. Per-repository .codex/.claude/.gemini folders are inventory entries, not cleanup targets.

## Codex customization and context guide

- Runtime-global instructions: Domus adapter source above renders R/codex/AGENTS.md, which
  points to shared ~/AGENTS.md. Repository and directory-scoped AGENTS files supply project rules.
- Config is split-owned: the modify template explicitly preserves application-owned bytes.
  Model and reasoning settings are app-owned in the inspected source. Change them through the
  app's owning surface; do not add competing atoms to the template.
- Hooks and rule files have their own source-owned modify surfaces. Project .codex/config.toml
  supplies max_threads/max_depth here; per-session tool availability is not implied by config alone.
- Skills and plugins have installed catalogs and provider projections. Fix their source/registry,
  validate the intended consumer, then apply through the installer; never patch a cache copy.
- This session demonstrably received the runtime-backed memory summary and skill catalog and read
  the runtime adapter. That does **not** mean all runtime files or all earlier chats were loaded.
  Files require explicit reads; installed/configured, authenticated, reachable and exercised are
  different claims.

## Safe recovery contract

The inspected historical Codex custody receipt has three aliases for the same destructive
delete-then-copy rollback command. **All three are revoked as recommendations. Do not execute them.**
Preserve the historical receipt unchanged as evidence; a later source-owner correction must mark
each command superseded and point to this staged protocol. V3's simpler rename-first proposal also
leaves a service gap if copying fails: validate the candidate **before** moving the current path.

1. Preserve and independently restore-test the backup through the custody owner. Same-volume clone
   checks and SQLite row counts alone do not establish this.
2. Quiesce only the exact participating writer through its supported lifecycle. Never signal a
   sibling human session. If that cannot be arranged, stage only and retain the active destination.
3. Prepare a fresh candidate in a unique directory, with conservative full-copy free-space
   headroom. The executable helper below never deletes or activates anything:

~~~sh
python3 docs/continuations/agent-surface-containment-20261018/stage-rollback.py --backup "$BACKUP" --current "$CURRENT" --stage "$NEW_STAGE"
python3 docs/continuations/agent-surface-containment-20261018/stage-rollback.py --backup "$BACKUP" --current "$CURRENT" --stage "$NEW_STAGE" --apply
~~~

The first command is read-only. The second uses macOS ditto into a fresh candidate and verifies
bytes, file modes, xattrs, and symlink targets against before/after backup manifests. Failure keeps
the current destination and partial candidate. Success is **staging only**; ACL/hardlink fidelity,
database consistency and native restoration are still separate checks. For SQLite, use its backup
API or a proven quiesced database+WAL snapshot; run integrity checks and baseline row-ID/count
comparisons on the candidate before activation. Never assert consistency from clone/copy alone.

4. The owning provider adapter must implement an exclusive cutover transaction: recheck that the
   live destination and backup still match the reviewed identities, retain the current destination
   under a collision-refusing recovery name, then activate the already validated candidate using
   same-filesystem no-replace rename primitives. Journal each step durably. If activation fails,
   restore the retained current path without overwriting any newly appeared path; otherwise stop
   with both paths preserved. Ordinary unguarded mv / ln -f is not that transaction.
5. Keep post-cutover new history separately. Do not merge SQLite stores or overwrite divergent
   histories blindly. Test a synthetic new-history sentinel, injected copy/activation failure,
   collision and replay. No disposal of either retained tree belongs to this handoff.

## Staged work packets and acceptance

| Stage | Owner / allowed changes | Run and evidence | Stop condition |
|---|---|---|---|
| A — evidence | This Limen PR; census tools, plan and counts receipt | Fixture checks, full-root scan ledger, integrity verifier, private publication readback | Any error/pending root remains a measured census gap; never report exhaustive success |
| B — census integration | Domus Phase B from #502; launcher/healthcheck and instruction-surface manifest | Import exact directory/alias identities, classify each with source owner and consumers, explicit unknown rows; coverage test plants a directory deeper than four levels | No green inventory with inaccessible/unclassified required surfaces |
| C — recovery correction | Domus preservation owner plus Limen #2848; historical receipt supersession, staged adapter | Independent restoration, candidate integrity, quiescence, all failure/replay cases, current history sentinel | No active-path mutation without all predicates |
| D — config convergence | Existing provider/skills owners in mapping | Secret-safe isolated render, effective-key comparison, scoped tests once, targeted chezmoi diff/apply, readback, second no-change render | Unknown fields, competing writer, authentication or discovery gaps remain explicit |
| E — optional retirement | Existing custody/rollout owner only | Exact parity, independent restoration, complete consumer census, inactive writer and Step 8 acceptance | This plan grants no deletion authority |

The original six findings are homed by this revision, not by a response-only apology.
For each future stage allow one 30-minute attempt, including at most ten minutes of verification;
one retry only after relevant inputs change. Keep unfinished tasks open under their existing owners.
Session release, complete directory coverage, config deployment and migration completion are
separate predicates. See the companion session receipt for the actual release outcome.
