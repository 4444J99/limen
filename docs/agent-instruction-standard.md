# The Agent-Instruction Standard ("agent-all")

> **Portal note.** This file is the durable answer to a recurring design question:
> *"how should our agent-instruction files (`AGENTS.md` / `CLAUDE.md` / `GEMINI.md` /
> `copilot-instructions`) be standardized, and where is the canonical **agent-all**?"*
> This is the committed answer, so it is summoned into sessions instead of re-derived and
> lost. If the standard is wrong, fix it here.

---

## TL;DR — the standard is two layers, and both already exist

There is **no missing "agent-all" repo to build**. The capability exists as two orthogonal
layers. The job is to **converge on them, not rebuild** them.

## File roles and boundaries

| Surface | Owns | Must not own |
|---------|------|--------------|
| `AGENTS.md` | Cross-agent protocol: operating modes, task states, budget/claim rules, safety, `dispatch_log` | Tool-specific personality or merge cadence |
| `CLAUDE.md` | Claude Code execution discipline, closeout, credential handling, merge policy, output style | Canonical status vocabulary or task-state schema |
| `GEMINI.md` | Conductor/Gemini MCP workflow, worktree spawning, PR babysitting mechanics | Independent task lifecycle rules |
| `CONTRIBUTING.md` | Human setup, style, gates, branch/PR requirements | Agent dispatch protocol |
| `docs/deployment.md` | Production deployment variables, commands, and safety checks | Agent task claiming or lifecycle state |
| Generated templates | Starter guidance for other tools/editors | Repo-specific truth copied out of date |

Any new instruction surface must declare which file it defers to and which behavior it uniquely
owns. If it repeats task states, precedence, agent names, or safety rules, add a drift check or link
back to `AGENTS.md` instead.

## Change procedure

1. Update the owning source file, not every surface by hand.
2. If the change touches states, precedence, agent names, referenced scripts, or examples, update
   `scripts/check-agent-docs.py`.
3. If the human correction changes workflow, priority, ownership, cadence, evidence, or acceptance
   criteria, propagate it through a durable surface future agents read: protocol doc, TABVLARIVS
   ticket, task packet, PR body, receipt, or explicit blocker. A chat-only apology is not enough.
4. Do not gate routine engineering mechanics on the human. The human owns ideal forms, priorities,
   taste, and human-risk decisions; agents own implementation choices, tests, cleanup mechanics, and
   best-practice tradeoffs when the repo evidence supports a path.
5. Preserve full lifecycle closure. A prompt, idea, viewpoint, branch, worktree, scratch root, or
   lane closes only as shipped, open PR, pushed plan/task, preservation receipt with next owner, or
   explicit blocker. No-diff, timeout, stale, or context-loss is not closure by itself.
6. Keep examples machine-checkable where practical.
7. Keep direct-session behavior distinct from dispatch-mode behavior.
8. Prefer bounded loops, explicit evidence, and append-only history over prose promises.
9. Treat the full prompt corpus as a concurrent control plane, not a competing work lane. Preserve
   individual ask/correction lineage, rank unresolved atoms by operator emphasis and systemic impact,
   prove completion from owner receipts, and keep sound in-flight execution moving within resource
   bounds while the corpus is refreshed. Do not require the human to restate settled intent.
10. End every closeout and begin every autonomous initiative with one continuation capsule. Use the
    canonical worktree launcher for repository-backed work; when no repository is the logical owner,
    use an isolated owner-native workspace or remote receipt rather than manufacturing a fake
    worktree. Its README fixes intent, authorities, prohibitions, predicates, and owner lineage; live
    environment probes derive the lane and ending. The closeout must print one launch command and
    make the capsule remotely durable. Never hard-code a future model, provider table, task count, or
    desired terminal verdict into the capsule.
11. Apply `AGENTS.md` → Bounded Composition to campaigns, CI, generated artifacts, and handoffs.
    Aggregate entrypoints are thin fan-in layers over independently runnable modules with finite
    retries, bounded output, and durable receipts; they never duplicate successful children.

## Home-scope generated surfaces

`domus-genoma` also renders home/global instruction files such as `~/AGENTS.md`,
`~/.claude/CLAUDE.md`, Copilot instructions, Cursor rules, and Codex shims. Those are fallback
surfaces, not repo-local truth. Their manifest is:

```text
domus-genoma/dot_config/ai-context/agent-instruction-surfaces.json.tmpl
```

The invariant is simple: home-scope instructions may provide defaults, but inside a repository the
nearest project `AGENTS.md` owns project-specific protocol. Tool-specific generated files must
defer to that project contract and must not redefine Limen task states or dispatch semantics.

### Layer 1 — ecosystem-context (the real "agent-all" generator)

- **Where:** `a-organvm/organvm-engine/src/organvm_engine/contextmd/`
- **Mechanism:** marker-region injection. It rewrites only the content between
  `<!-- ORGANVM:AUTO:START -->` and `<!-- ORGANVM:AUTO:END -->`; everything outside the
  markers is hand-authored and preserved. Idempotent.
- **Source of truth:** `contextmd/templates.py` (REPO / AGENTS / ORGAN / WORKSPACE sections);
  rendered by `generator.py`, applied by `sync.py::sync_all()`.
- **Run:** `organvm context sync --write`
- **Drift check:** `organvm context sync --dry-run` (`cli/context.py::cmd_context_sync` →
  `contextmd/sync.py::sync_all()`). The separate
  `.github/workflows/ecosystem-sync-check.yml` runs `organvm ecosystem sync --dry-run` for
  `ecosystem.yaml` scaffolds; it is not the contextmd marker-section drift gate.
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

> **Scope boundary — the layers do not share task vocabulary (verified 2026-06-26).**
> organvm-engine has its **own** plan-tracking vocabulary via its IRF format (*Index Rerum
> Faciendarum*): canonical statuses `open · completed · blocked · archived`. Its
> `plans/atomizer.py` and `prompts/audit.py` emit/accept **`completed`** *by design* — it
> maps `## Completed` IRF sections and `[x]` checkboxes, writes only an internal
> `atomized-tasks.jsonl`, has **zero** imports of or plumbing to limen, and ~250 tests depend
> on it. So when auditing Layer 1 for "the same `completed` drift": **that is not drift — do
> not align it to limen's `done`.** Aligning would break organvm-engine's own governance and
> tests. Task-state vocabulary is **per-layer**: limen's `done` is canonical only for limen's
> dispatch lifecycle; IRF's `completed` is canonical only for organvm-engine's plan tracking.

---

## Precedence (when instructions conflict)

Mirror of `AGENTS.md → Precedence`, repeated here so the portal is self-contained:

1. System / developer / runtime constraints (the harness)
2. The human's explicit instructions for this session
3. `tasks.yaml` — the single source of truth for task **state**
4. `AGENTS.md` — the cross-agent dispatch **protocol**
5. Tool-specific charters (`CLAUDE.md`, `GEMINI.md`) — per-agent behavior
6. General repository docs (`README.md`, `docs/**`)

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

## Decision record: 2026-06-26 instruction critique

Recorded so the same instruction-design questions are not re-run from scratch next time.
Verdicts are against this repo's own philosophy: the charter is a single file deliberately
loaded every session, and "Definition of Done = an executable predicate, not prose."

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

## Historical context (portal index)

Selected prior prompts/sessions that dealt with the agent-instruction standard, so the intent is
captured durably. Sourced from a sweep of session transcripts (`~/.claude/projects`).

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
