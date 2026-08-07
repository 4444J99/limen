> **PROVENANCE / VERDICT (2026-08-06 reconciliation — plan `docs/plans/2026-08-06-prima-materia-reconciliation.md`, issue #1934).**
> Externally-drafted charter, received from an out-of-estate brainstorm session via
> `~/Downloads/consolidation-directive.md`. Archived verbatim below; **not adopted**.
> Disposition: MERGE into the ratified 2026-07-30 lineage
> (`docs/plans/2026-07-30-portvs-astra-consolidation.md`), which already ruled: PORTVS
> exists (`organvm/portvs`; "a second portal is the named failure mode"); the rename
> decision was `limen → astra` with `stratvm` only as fallback (now lever
> `L-NAME-RULING-LIMEN-ASTRA-STRATVM`); SVBTERRANEA is a stratum (archive-in-place), not
> an org or directory tree; domains live in persistent directories while summoned work
> stays worktree-governed (the Meeseeks law + `IF-SESSION-NON-CONTENTION` — this
> charter's "never git worktrees" is rejected); hot-cache mechanics are shipped
> (`scripts/verify-hot-cache.sh`, `IF-HOT-CACHE`); `NAMES.md` duplicates
> `spec/index-nominum/roll.yaml`. Disk survey 2026-08-06: the legacy names this charter
> expects (`portals`, `alignment`) exist nowhere; its premises describe a disk that isn't
> there. Precedent: `PREC-2026-08-06-external-charter-reconciles-before-adoption`.

# CONSOLIDATION DIRECTIVE — portvs · stratvm · svbterranea

> **Use:** paste this entire file as the opening prompt in a fresh Claude Code session started at the workspace root. Read fully before acting. This is a **complete-or-report** run: every phase ends at a verification gate, and nothing is skipped silently.

## 1 · CONTEXT

You are consolidating the local footprint of **{OS.me}** (the meta-organvm architecture). The operator is a philosopher, artist, and systems-thinker — not a traditional engineer. The architecture is specified conceptually; you translate it into correct engineering without asking him to arbitrate implementation details.

The system's standing doctrine is already written: **REMOTE_IS_CANONICAL · LOCAL_IS_WORKSPACE · CACHE_IS_DISPOSABLE.** Your job in this run is to make that doctrine *physically true*. The Platonic framing the system uses: the remote is the Form; any local checkout is the shadow on the cave wall. The local machine is a **hot cache** — a terminal at a library the operator jacks into. It must hold zero irreplaceable state, summon everything on demand, and extract cleanly on exit.

Previous cleanup runs stalled partway. The known failure modes — hesitation before destructive steps, ambiguity resolved by quietly shrinking scope, context loss between sessions — each have a countermeasure below. Honor them.

## 2 · PRIME DIRECTIVES

1. **Complete or report.** Finish every phase, or enumerate exactly what is blocked and why in the final report. No silent omissions. "Partially done" without an itemized remainder is a failure state.
2. **Nothing is destroyed.** "Delete" means *move to `_condemned/<ISO-date>/` with a manifest line*. Only the operator empties condemned. This removes every reason to pause for permission mid-run.
3. **Remote is truth.** Before anything moves, verify it is committed and pushed. Unpushed work gets rescued (Phase 1) — never dropped.
4. **One credential session.** Authenticate once up front (1Password CLI biometric session; `op run` + env templates for anything scripted). If a step would trigger interactive credential prompts repeatedly, the step is wrong — restructure it.
5. **Resumable.** Keep `CONSOLIDATION_PROGRESS.md` current at every gate, so a fresh session can resume mid-run without re-briefing.
6. **The screener test.** The end state must read, to a hiring reviewer with 30 seconds, as deliberate architecture — not sprawl.
7. **Reality beats directive.** If something on disk contradicts this document, do not improvise silently: log the conflict in the progress file, choose the least destructive interpretation, and continue.

## 3 · TARGET ARCHITECTURE

Three layers. Latin names, classical v-for-u orthography, per the standing naming protocol.

| Layer | Essence | Contains |
|---|---|---|
| **portvs** — the harbor | Arrival and departure. Jack in, jack out. | Bootstrap script, machine provisioning, auth wiring (SSH · GPG · 1Password), the `jack-in` and `eject` commands |
| **stratvm** — the laid-down layer | The law. Written once, referenced everywhere. | Naming protocol, semver policy, routing/labeling/containment rules, repo + skill templates, secrets-access pattern, taxonomies. **Supersedes limen.** |
| **svbterranea** — the underground | The work itself. | One plain directory per domain surface. **Never git worktrees.** |

**Legacy vocabulary you may find on disk → canonical:**

| Found on disk | Was | Becomes |
|---|---|---|
| `portals` | old name for the entry layer | `portvs` |
| `alignment` | old container for domain surfaces | `svbterranea/` |
| `limen` | old governance repo | `stratvm` (content migrated, limen archived) |
| any git worktree | pruning hazard | standalone directory under `svbterranea/` |

**Canonical local layout** (detect the actual `<ROOT>` from current conventions; propose it in Phase 0):

```
<ROOT>/
├── portvs/
├── stratvm/
├── svbterranea/
│   ├── <domain-1>/
│   ├── <domain-2>/
│   └── …
├── _condemned/<date>/        # quarantine — gitignored, operator-emptied
├── CONSOLIDATION_AUDIT.md
├── CONSOLIDATION_PROGRESS.md
└── MOVES_MANIFEST.md
```

**Resolve in Phase 0, then proceed on your own determination:** whether svbterranea domains are independent repos cloned side-by-side (expected, given the multi-org GitHub Enterprise layout) or subdirectories of one repo. Inspect the remotes, state your call in the audit, and act on it.

## 4 · PHASES

### Phase 0 — Discovery *(read-only)*
- Inventory: the limen repo; the workspace directory; every git repo present; `git worktree list` for each; all uncommitted/unpushed work; duplicates; stray files.
- Classify **every** top-level item: `PORTVS · STRATVM · DOMAIN:<name> · ARCHIVE · CONDEMNED`. No `UNKNOWN` survives Phase 0 — force a one-line reasoned decision on each.
- Write `CONSOLIDATION_AUDIT.md`: tree, classifications, unpushed-work list, worktree list, proposed `<ROOT>`, monorepo-vs-multirepo determination.
- **Gate 0:** audit exists; zero unclassified items.

### Phase 1 — Rescue the unpushed
- Every repo with uncommitted or unpushed work: commit to `rescue/<date>-<slug>`, push it.
- **Gate 1:** every repo clean and remote-synced, or exceptions itemized in the progress file.

### Phase 2 — Worktrees → directories
- Per worktree: confirm its branch exists on the remote → materialize as a standalone directory under `svbterranea/` (fresh clone or move) → verify history intact → only then `git worktree remove` and `prune`.
- **Gate 2:** `git worktree list` returns empty everywhere; each former worktree has a standalone, remote-synced directory.

### Phase 3 — limen → stratvm
- Create **stratvm** (rename limen's repo or create fresh — whichever preserves history best).
- Migrate only what is *law*: rules, protocols, templates, policies. Domain work found inside limen → its `svbterranea/<domain>/`. Junk → `_condemned/`.
- Seed stratvm with five artifacts, so the rules are never reinvented again:
  - `NAMING.md` — Latin, v-for-u orthography, short (ideally two-syllable) single words; casing rules; repo/directory/branch patterns
  - `VERSIONING.md` — the semver policy and where it applies
  - `ROUTING.md` — what goes where: the Phase-0 classification rules, made permanent
  - `SECRETS.md` — the one-session credential pattern; `op run` env-template usage; what never touches disk
  - `TEMPLATES/` — repo skeleton, README skeleton, SKILL.md skeleton
- Archive limen on GitHub once migration is verified — a threshold exists to be crossed and left behind.
- **Gate 3:** stratvm live with all five seeds; limen contains nothing unclassified; limen archived.

### Phase 4 — Sort the workspace
- Execute the Phase-0 classification: every stray item moves to `portvs/`, `stratvm/`, `svbterranea/<domain>/`, or `_condemned/<date>/`.
- Every move appends an `old → new` line to `MOVES_MANIFEST.md`.
- **Gate 4:** `<ROOT>` contains exactly the canonical layout plus the three run-files, nothing else. Paste the `ls` output into the progress file as evidence.

### Phase 5 — Hot-cache mechanics
- **Toolchains:** per-repo declarative manifests (`mise.toml`, or justify one alternative in stratvm and use it everywhere). No globally pinned Pythons or Nodes — versions resolve per-project on demand, cache centrally, evict freely. Remove the global pins that exist today.
- **`portvs/jack-in`:** one command on a bare machine → single credential session → clone stratvm → materialize any named domain from its remote. Idempotent.
- **`portvs/eject`:** verify everything committed and pushed → print anything that would be lost → wipe local clones. Dry-run is the default mode.
- **Gate 5:** in a temp directory, run jack-in for one real domain and an eject dry-run; paste both logs into the report.

### Phase 6 — Presentation pass *(the screener test)*
- README at each of the three roots: one tight paragraph — what it is and how it relates to the other two, in plain language a non-specialist reviewer parses in seconds. No lore walls.
- GitHub descriptions and topics updated to match; naming made consistent per `NAMING.md`; anything not portfolio-ready goes private; finished-but-inactive gets archived. (Public = showcase. Private = valuable, not showcase. Archive = done, worth keeping.)
- **Gate 6:** state in the report, in two sentences, what a screener now sees in 30 seconds.

## 5 · OUT OF SCOPE — DO NOT TOUCH

- **External hard drives.** Do not mount, scan, or reference them. Separate future run.
- Emptying `_condemned/` — operator only.
- Editing domain *content* — this run is structural, not editorial.

## 6 · FINAL REPORT

Write `CONSOLIDATION_REPORT.md`: phases completed; each gate's evidence (actual command output); paths of the audit and manifest; an itemized blocked/deferred list with reasons; and the exact follow-up prompt for the external-drive pass, pre-written and ready to paste.
