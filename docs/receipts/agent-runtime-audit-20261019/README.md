# Agent runtime audit - 2026-10-19

Owner: [Limen #2848](https://github.com/4444J99/limen/issues/2848).
This receipt extends the [v3 reconciliation plan](../../plans/2026-10-18-agent-surface-reconciliation-v3.md);
it does not replace its architecture or authorize its implementation.

## Result and authority

The shared runtime containment predicate passed. Five source-rendered settings files
matched their deployed semantics. The next work is narrower ownership, consumer-path
and acceptance reconciliation, with physical capacity and custody kept separate.
No live apply, deletion, quarantine, agent restart or session restoration was
performed. No fresh native vendor chat was launched for acceptance testing. The user later requested a team; two native read-only audit peers
reviewed configuration and storage independently.

Observations began at 13:18 UTC; each evidence item retains its own timestamp. Exact commands, metrics and limits are in
[observations.json](observations.json). They describe this host at those times,
not an estate-wide or continuing health guarantee.

## Source and runtime map

`$RT` is the effective shared root declared by `~/.zshenv`;
`$DOMUS` is the chezmoi source returned by `chezmoi source-path`.
The live source root was read without modifying its unrelated dirty state.

| Surface | Installed version observed | Effective consumer surface | Source / ownership | Acceptance |
|---|---|---|---|---|
| Claude Code | 2.1.303 | `$CLAUDE_CONFIG_DIR=$RT/claude` | Domus `private_claude/modify_private_settings.json.tmpl`; split app/cartridge ownership | Settings render matches semantics; current native skill/MCP discovery not exercised |
| Codex CLI / bundled client | 0.163.0 / 0.163.0-alpha.10.2 | `$CODEX_HOME=$RT/codex` | Domus `private_codex/modify_private_config.toml.tmpl`; app owns model/UI/transport blocks | Render byte-equal; this audit exercised broker capability reads and registration only |
| Gemini CLI | 0.61.0 (package metadata) | `$GEMINI_CLI_HOME=$RT/gemini/home`, then `.gemini/` | Domus named observation-hook modifier; other settings preserved | Render byte-equal; auth and native discovery untested |
| OpenCode | 2.0.32 | Config at `~/.config/opencode/opencode.jsonc`; launcher-scoped XDG state under `$RT/opencode` | App/ianva config; Domus launcher, shim and observer plugin | Version and source path observed; gateway auth/native discovery untested |
| Copilot CLI | 1.0.98 | `~/.copilot -> $RT/copilot/dot-copilot`; launcher adds agent-council config | Domus MCP template and launcher, app-owned mutable state | Base MCP render byte-equal; combined precedence/native discovery untested |
| Cursor | Unverified | Retained `~/.cursor -> $RT/cursor/dot-cursor` | Domus hook modifier; retained app skills/state | Hook render byte-equal; no launcher on PATH or app found at two standard paths |
| Antigravity (adjacent dependency) | agy 1.4.2 | `~/.gemini` doorway; its `config` resolves to `$RT/antigravity/config` | Domus adapters; vendor mutable state retained | Path and version observed; prior acceptance receipt remains historical |

The `private_claude`, `private_codex` and other source paths in this table are
under `$DOMUS/Workspace/limen/private_dot_agent-runtime/`.
Home aliases are compatibility doorways. The five tested settings files are real
files at their effective destinations. Future convergence edits the owning source
and renders real configuration; no additional link-based cutover is proposed.

## Source comparison and precedence

Private renders used a temporary mode-0700 directory and mode-0600 files.
`chezmoi cat <target>` output was parsed in memory; no configuration values were
printed. All five target files were unchanged during their render comparison.
The temporary render directory was removed by the context manager.

| Compared source output | Semantic changed keys | Byte comparison |
|---|---|---|
| Claude settings | None | Formatting differs |
| Codex config | None | Equal |
| Gemini settings | None | Equal |
| Cursor hooks | None | Equal |
| Copilot base MCP config | None | Equal |

This proves convergence to the selected local source, not native behavior or
equivalence to every legacy value. The deployed runtime implementation and launcher
also byte-match their owning source files.

Claude plugin flags belong to the app under the current ownership registry:
16 entries are present and all are false. The v3 plan's "16 enabled" statement is
outdated. The modifier preserves those decisions; a broad apply will not restore
plugin enablement. Their intent/authentication remains unresolved, so no bulk
enable or removal is proposed.

Codex has 15 explicit MCP entries (14 enabled or default-enabled) and 19 plugin
entries (13 enabled). These counts are configuration evidence. Gemini's legacy
settings lack the two observation events found in its effective settings; both
retain the ianva entry. Claude's effective native global metadata has no top-level
MCP entries, while its retained legacy global metadata lists four. The registry
explicitly retired that injection because it never reached live sessions. This is
preserved historical configuration, not evidence of four previously working
capabilities being lost. Fresh native discovery remains unmeasured.

## Findings, owners and acceptance

The configuration peer compared ten selected active instruction/manifest/skills
surfaces with their private source render: all ten were byte-equal. This covers
the home and config AGENTS entry points, provider shims, OpenCode and Copilot
instructions, Antigravity rules/skills and the instruction manifest. It proves
deployment content parity, not fresh-session retrieval. Cursor has no active
instruction row in that manifest.

| Finding | Observed evidence | Owner / next predicate |
|---|---|---|
| Cursor MCP source targets a different directory | Source `dot_local/share/private_cursor/mcp.json.tmpl` renders `~/.local/share/cursor/mcp.json` with github/jupyter/serena; `~/.cursor/mcp.json` and inspected project `.cursor/` roots are absent | Domus config owner, routed by #2848: map source to the supported consumer path as real configuration, privately render, then prove native discovery; retain old state |
| OpenCode ownership misses the selected JSONC path | The managed launcher selects `opencode.jsonc`; config-ownership/ignore declare the absent `opencode.json`; the instruction manifest's repair still seeds historical JSON | Domus config-ownership and instruction-manifest owners: declare the actual app-owned path, preserve contents, validate registry/ignore/source/repair alignment |
| Copilot inventory omits its additional launcher layer | The source-matching shim adds `agent-council` through a separate MCP file, alongside the eight base entries; supporting files exist but were not exercised | Domus launcher/MCP estate owner: include the effective layer and resolve name/registration identity, then bounded native discovery; do not assume replacement or disable either layer |
| Plan describes Claude plugins as enabled | Live 0/16 enabled; current modifier intentionally preserves app plugin flags | v3 documentation / app owner: correct snapshot, resolve intent and readiness per capability; no bulk enablement |
| OpenCode October archive is staged without a complete receipt | External October 18 DB family exists; two local intake attempts have compressed indexes but no manifest; tracked intake doc/log remain July-only | `aw-opencode-db-corpus-intake-0709`: reconcile those attempts before another transfer, then integrity, independent readback and restoration |
| Bare OpenCode intake command has side effects and cannot prove archival | Source writes an index without `--write`; DB backup requires `--archive`, and manifest/tracked output requires `--write` | Existing intake owner: review explicit roots and `--archive --hash-archive --write` under admission, then verify the receipt and restoration; do not run the v3 bare command as a check |
| Shared-state ownership remains incomplete | `.recode` classification stage exists, but no producing app/consumer/retention/restore identity is established | #2848 / Domus lifecycle: complete classification before any move |
| Storage and rollout prose lags live implementation | Domus lifecycle still describes fixed vendor quotas; original watch evidence is `coverage_failure` and restoration unverified while #2848 still calls it active | Source documentation / #2848: preserve the failed window, update current semantics and require fresh consumer acceptance |

Cursor documents global `~/.cursor/mcp.json` and project `.cursor/mcp.json`
in its [MCP configuration guide](https://prod.cursor.com/help/customization/mcp).
The current source destination is outside those documented file paths; any
alternative dynamic registration remains untested. Copilot's contained instruction
path is supported by its [custom instructions guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions);
do not extrapolate a universal closest-file-wins rule to its combined instruction
surfaces.

The OpenCode reader resolver correction is already merged in Limen #3029
(`d899a2e5e799`, October 18 08:33 UTC). That code publication is distinct from
the incomplete archive receipt. The October snapshot's size matches the live DB
size observed here, but no content-equivalence or independent restore claim follows.

Historical custody receipt fields still contain delete-first rollback commands.
The appended v2 correction supersedes them: never replay those fields. An APFS
clone is writable and same-volume; it is not independent custody. Shared extents
stay allocated, while divergent/unshared allocation needs measurement. Moving
outside an apparent-byte accounting root can change that accounting without
proving physical disk recovery.

## Storage and cleanup review

At 13:22 UTC, `domus-agent-runtime check --json` exited 0 with a complete census,
177,961 files, no scan errors and no unauthorized legacy roots. It measured
25,535,235,725 apparent bytes: 16,310,255,110 in the four named vendor buckets and
9,224,980,615 shared bytes. Copilot, Cursor and other top-level state are still
included in the total, even though they lack separate named vendor rows.

Physical free space was 14,367,776,768 bytes (about 13.4 GiB). The pool admitted
growth with a zero-byte reserve and 201,326,592 bytes outstanding. This is a
disk-aware growth decision; its reported capacity is not a fixed vendor quota.
The separate `df` observation reported 97% used. Allocated blocks from `du`
and apparent bytes from the runtime census are different measures and timestamps.

| Candidate / state | Owner and value | Regeneration / recovery | Disposition |
|---|---|---|---|
| Native sessions, memories, databases and WAL/SHM families | Vendor history and active user state | Restore and native reader acceptance required | Retain; no deletion eligibility established |
| Live OpenCode DB, 3,072,540,672 bytes | Existing corpus-intake owner | Consistent DB-family snapshot plus manifest and restore proof | Retain; October archive staging is not a complete custody receipt |
| Legacy OpenCode DB, 8,257,536 bytes | Legacy reader/custody owner | Subset/equivalence to live DB unverified | Retain; size and age prove no redundancy |
| Shared `.recode/changes.db`, 2,077,659,136 bytes | Protected, unclassified shared state; #2848 routes classification | Producing app, consumers, retention and restoration mapping required | Retain; not a generic cache |
| Claude legacy-home / legacy metadata | Existing v3 retirement lane | Independent custody and safe rename-aside rollback | Retain; doorway presence is not retirement approval |
| Downloaded/plugin caches and Claude VM base images | Package/maintenance owners; VM sessiondata is protected | Exact base/version identity, inactive-use, reconstruction and native cold-start predicates | Review candidates only; no blanket reclaim claim |
| Dirty or active worktrees | Current session owners | Live remote parity, custody and review closure | Preserve; no reaping by this audit |
| Loose exports and custody partials | Existing custody lane | Integrity manifests and receiving-owner receipt | Preserve; moving them does not reclaim physical blocks |

The root process-name census observed active Claude, Codex, OpenCode, ChatGPT and
Domus hosts. It used executable names only, so node-launched providers may be
invisible. Counts do not establish session health and no process was signaled.

## Bounded convergence handoff

The existing owner remains #2848 and the v3 plan. A later implementation packet
must select one source writer and one isolated checkout, preserve all app-owned
keys and unknown capabilities, and capture exact before-state and source revision.

1. Reconcile consumer paths and ownership entries before touching deployed state:
   OpenCode's selected JSONC path, Cursor's MCP destination, and Copilot's additional
   agent-council layer.
2. Resolve legacy-to-effective key semantics and the Claude plugin/global-MCP
   differences through current intent and loader evidence. Preserve intentional
   app preferences and all unresolved capabilities.
3. Render only the implicated source privately. Compare semantic changed-key
   paths and all preserved sections; do not expose credential values.
4. For any separately authorized cutover, preserve an exact preimage and use the
   owner's supported apply path. Rollback preserves the new destination by
   renaming it aside before restoring and checking the preimage. Never replay
   the historical delete-first rollback.
5. Read back source and destination, then observe native discovery, harmless
   authenticated reads and an existing conversation restore where relevant.
   Source validation, publication, deployment and application acceptance remain
   separate receipts.
6. Reconcile the shared-pool reserve and custody owner before any storage action.
   No amount of plan publication authorizes native history deletion.

Implementation is not authorized by this audit invocation. A future bounded
packet has a 30-minute attempt including at most 10 minutes of verification,
one corrective retry only after an input changes, source-scoped checks, and an
explicit retained-state/rollback owner. Stop at a named external gate while
completing independent reversible work.

## Repository and execution evidence

| Repository | Observed local state | Remote reconciliation |
|---|---|---|
| Limen live checkout | `b6a4f208480d`; unrelated `.trunk/` untracked | `origin/main` cached comparison was 11 commits ahead; audit worktree starts at live remote `b75de04851f8` |
| Domus source | `dd00bfc569fe`; unrelated `.serena/project.yml` modified | Live remote `a9495ce59580` is one commit ahead; only Gemini extension installer/docs/tests differ |

The newer Domus commit gates extension installation behind an explicit opt-in,
bounds each install and keeps consent separate (PR #541). This audit did not run
that installer or treat extension configuration as installation success.
Limen #2848 is open; research PR #3081 is merged; Domus skills PR #436 is open.

The native session was registered as human-protected. Read admission packets
returned HTTP 409 `conduct_rejected` without a reason, including after native
identity/scope correction; no run/lease/child was accepted. The later explicit
"launch team" instruction produced two native read-only peers. No broker
reservation or terminal child receipt is claimed.

Hook denials were recorded separately from broker admission. Explicit scoped
working-directory syntax enabled the owned audit branch. An attempted external
config-ownership predicate was blocked by target-scope enforcement; direct
execution then exited 126 because the source file is not executable. It is not a
passing check. Bare shared-context verification exited 2 because it requires a
plan; no shared-context deployment was attempted.


## Evidence map

| Claim | Source inspected |
|---|---|
| Cursor source destination | Domus `dot_local/share/private_cursor/mcp.json.tmpl:8`; retained destination metadata |
| OpenCode ownership and repair | Domus `.chezmoidata/config-ownership.json:326`, `.chezmoiignore:253`, instruction-manifest template `:244`, runtime adapter `:605` |
| Copilot additional layer | Domus `dot_local/libexec/domus/shims/executable_copilot:4`, agent-council MCP template `:2`, config registry `:2001` |
| Claude legacy MCP retirement | Domus config ownership registry `:238` |
| Intake side effects / archival flags | Limen `scripts/opencode-db-corpus-intake.py:220`, `:241`, `:246`, `:355` |
| Stale storage lifecycle semantics | Domus `docs/runtime-maintenance-lifecycle.md:18`, `:36`, `:97`; deployed adapter `:1008` |
| Original watch and restore limits | Limen `docs/reviews/shared-agent-os-evidence-20261015.json:61`, `:213`; live #2848 readback |
| Protected VM data / base acceptance | Domus home-surface manifest `:6`, `executable_domus-claude-vm-lifecycle:48` |

References denote the observed local revisions listed above. Private archive attempt
paths, raw hashes and payloads were not copied into the report. Metadata observations
of those attempts remain distinct from validated custody.

## Publication and verification

Audit findings and the implementation handoff are this session's work products.
Live runtime behavior, cleanup and the larger rollout remain with their existing
owners. The final scoped check and publication state are recorded with this
receipt; no deployment or cleanup success is claimed.
