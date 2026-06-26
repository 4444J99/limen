# The Agent-Instruction Standard ("agent-all")

> **Portal note.** This file is the durable home for a question that keeps recurring in
> chat: *"how should our agent-instruction files (`AGENTS.md` / `CLAUDE.md` / `GEMINI.md` /
> `copilot-instructions`) be standardized, and where is the canonical **agent-all**?"* You
> have raised it many times — *"we have built this many times in different ways"*
> (2026-06-23). This is the committed answer, so it is **summoned into every session instead
> of re-derived and lost**. If you find yourself re-litigating the agent-instruction files,
> read this first; if it is wrong, fix it here.

---

## TL;DR — the standard is two layers, and both already exist

There is **no missing "agent-all" repo to build**. The capability exists as two orthogonal
layers. The job is to **converge on them, not rebuild** them.

### Layer 1 — ecosystem-context (the real "agent-all" generator)

- **Where:** `a-organvm/organvm-engine/src/organvm_engine/contextmd/`
- **Mechanism:** marker-region injection. It rewrites only the content between
  `<!-- ORGANVM:AUTO:START -->` and `<!-- ORGANVM:AUTO:END -->`; everything outside the
  markers is hand-authored and preserved. Idempotent.
- **Source of truth:** `contextmd/templates.py` (REPO / AGENTS / ORGAN / WORKSPACE sections);
  rendered by `generator.py`, applied by `sync.py::sync_all()`.
- **Run:** `organvm context sync --write`
- **Drift check:** `organvm ecosystem sync --dry-run` (`fossil/drift.py` +
  `.github/workflows/ecosystem-sync-check.yml`, on push to `main`).
- **Coverage:** manages `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` across ~190 files at
  workspace / organ / repo level (~73–85% auto-generated).
- **What it injects:** shared org/ecosystem context (system library, handoff status,
  network/ontology, variables). It does **not** define the limen task lifecycle.

### Layer 2 — task-lifecycle + dispatch-protocol (lives in limen)

- **Where:** this repo's root — `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`.
- **Provenance:** **hand-authored sources** (no `ORGANVM:AUTO` markers). They are canonical
  for *how a task moves* and how each agent behaves.
  - `AGENTS.md` — the cross-agent dispatch contract: **Startup Checklist**, **Precedence**,
    **Task States**, the session rituals, the `dispatch_log` format.
  - `CLAUDE.md` — the Claude Code operating charter (merge/branch protocol, closeout,
    credentials-are-organ-owned, gate matrix).
  - `GEMINI.md` — the conductor swarm's MCP integration + worktree/PR-babysitting lifecycle.
- **Bound to code:** the task-state vocabulary is defined once in
  `mcp/src/limen_mcp/server.py` (`VALID_STATUSES`) and the docs are verified against it by
  `scripts/check-agent-docs.py`.

**The two layers are orthogonal.** ORGANVM owns *ecosystem context*; limen owns *task
lifecycle*. Neither absorbs the other, and there is no third generator to write.

---

## Precedence (when instructions conflict)

Mirror of `AGENTS.md → Precedence`, repeated here so the portal is self-contained:

1. System / developer / runtime constraints (the harness)
2. The human's explicit instructions for this session
3. `tasks.yaml` — single source of truth for task **state**
4. `AGENTS.md` — the cross-agent dispatch **protocol**
5. Tool charters (`CLAUDE.md`, `GEMINI.md`) — per-agent behavior
6. General repo docs (`README.md`, `docs/**`)

---

## The canonical task states

Defined in `mcp/src/limen_mcp/server.py` → `VALID_STATUSES`, enumerated in
`AGENTS.md → Task States`, and checked by `scripts/check-agent-docs.py`:

`open` · `dispatched` · `in_progress` · `done` · `failed` · `failed_blocked` ·
`needs_human` · `archived`

There is **no** `completed` state — use `done`.

---

## What was wrong, and is now fixed (2026-06-26)

| Drift | Fix |
|-------|-----|
| `GEMINI.md` documented a `completed` status the MCP server never accepted | → `done`; forbidden token now predicate-checked |
| `AGENTS.md` enumerated only 5 of the 8 canonical states | → full **Task States** table, verified against `VALID_STATUSES` |
| No explicit precedence ladder or fast-path startup checklist | → added **Precedence** + **Startup Checklist** to `AGENTS.md` |
| `CONTRIBUTING.md` was a stray copy ("Contributing to ORGAN-V", essay topics) | → rewritten for limen (layout, gate matrix, branch/merge protocol) |
| `CLAUDE.md` lifecycle said "plus `failed`/`stale`" (`stale` is not a status) | → corrected to the real terminal states + release-to-`open` |

### The drift predicate (why this stays fixed)

`scripts/check-agent-docs.py` (wired into `scripts/verify-whole.sh`) parses `VALID_STATUSES`,
asserts the `AGENTS.md` **Task States** table equals it exactly, and forbids the `completed`
token in all three docs. **Exit 0 ⟺ docs and code agree.** This is the autopoietic guarantee:
the instruction files can no longer silently drift from the code.

---

## Codex's 2026-06-26 critique — adjudicated

Recorded so the same generic advice is not re-run from scratch next time. Verdicts are
against this repo's own philosophy (the charter is a single file deliberately loaded every
session; "Definition of Done = an executable predicate, not prose").

| # | Codex point | Verdict | Why |
|---|-------------|---------|-----|
| 1 | Split files by audience | **Partial** | `CONTRIBUTING.md` (human) vs `AGENTS.md` (agent) split done. |
| 2 | `AGENTS.md` = short source of truth + precedence + states + checklist | **Accepted** | All added. |
| 3 | Shrink `CLAUDE.md`, move policy to `docs/operations/*` | **Rejected** | The charter is intentionally one file loaded every session; fragmenting it defeats that. It already cross-links (e.g. the architecture map → gate matrix). |
| 4 | Normalize `done`/`completed` terminology | **Accepted** | The only real drift was `GEMINI.md`; now predicate-enforced against `VALID_STATUSES`. |
| 5 | Machine-checkable examples; no stale dates | **Accepted** | Task States table is machine-checked; example timestamps made consistent. |
| 6 | Fast-path startup checklist | **Accepted** | Added to `AGENTS.md`. |
| 7 | Separate human/agent guidance; concrete commands in `CONTRIBUTING` | **Accepted** | Rewritten with the real gate matrix + layout. |
| 8 | State security/credential guidance once, link everywhere | **Already done** | `CLAUDE.md → Credentials Are Organ-Owned` + `creds-hydrate.py`. |
| 9 | Conflict-resolution order | **Accepted** | Added as **Precedence**. |
| 10 | Make each file testable / point to scripts | **Already the core tenet** | Charter's "Definition of Done"; reinforced by `check-agent-docs.py`. |

---

## The recurring asks (portal index)

Every prior prompt/session that dealt with the agent-instruction standard, so the intent is
captured durably. Sourced from a sweep of ~2,300 session transcripts (`~/.claude/projects`).

| Date | Session (under `~/.claude/projects/`) | The ask | Outcome |
|------|----------------------------------------|---------|---------|
| 2026-06-23 | `…indexed-baking-breeze/57fa1ead…` | "finally build the platform of pillars (config, tui, **agent-all**, terminal, vs code/antigravity configs, memories, plans, transcripts) — we have built this many times in different ways" | CONVERGE-not-rebuild program (P0+P1+P2); this file settles the agent-instruction pillar |
| 2026-06-23 | `…mighty-enchanting-pinwheel/45ef3e9f…` | "implement all these suggestions … Add a top-level `## Closeout Definition` … Add a `## Definition of Done`" to `CLAUDE.md` | Genesis of the current `CLAUDE.md` charter governance sections |
| 2026-06-25 | `…tender-sniffing-marshmallow/6b107f0b…` | "portvs/limen/session-meta/_arms/**agent-all**/tui/configs/extensions — these all belong together too, don't they?" | Ideal-form grouping of agent-all with session-meta/configs (wider pillars platform) |
| 2026-06-24 | `…indexed-baking-breeze/57fa1ead…` | "we need an insights-and-then-actions pillar/institution — avditor … consolidate into one monolith" | `avditor`/censor institution converging limen self-* surfaces |
| 2026-06-17 | `…/Volumes/Archive4T/9750bef7…` | `/init` a `CLAUDE.md` for the substrate-consolidation container | Per-repo charter authored (not a cross-repo convergence) |
| 2026-06-01 | `…limen-080-dc07/e6674792…` | LIMEN-080: refresh a stale ORGANVM-autogenerated `CLAUDE.md` tail | Confirms the Layer-1 autogen-tail mechanism |
| 2026-06-26 | this session | "how could claude.md, agents.md be improved? … there's an agent-all repo … build the thing" | This portal + the drift fixes + `check-agent-docs.py` |

---

## Roadmap note — the wider pillars platform

"agent-all" is one pillar of a larger platform you have described (config · tui · **agent-all**
· terminal · VS Code/Antigravity configs · memories · plans · transcripts). This file settles
the **agent-instruction** pillar. The broader convergence — and the standing rule that a
capability appearing ~7× means **converge, do not rebuild** — is the Pillars-platform program.
When extending the agent-instruction standard to non-Claude editors (VS Code, Antigravity),
do it as Layer-1 templates in `organvm-engine` or as new hand-authored sources here, and add
the new checks to `scripts/check-agent-docs.py` — never as a competing generator.
