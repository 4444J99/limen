> **PROVENANCE / VERDICT (2026-08-06 reconciliation — plan `docs/plans/2026-08-06-prima-materia-reconciliation.md`, issue #1934).**
> Externally-drafted charter, received from an out-of-estate brainstorm session via
> `~/Downloads/OPERATION_PRIMA_MATERIA.md`. Archived verbatim below; **not adopted**.
> Disposition: MERGE into the ratified 2026-07-30 lineage
> (`docs/plans/2026-07-30-portvs-astra-consolidation.md`). Its census/intake/triage/
> consolidate/surface program duplicates `institutio/governance/corpora.yaml` +
> `scripts/corpus_resolve.py` (corpus homes), the prompt-atom ledger + `atom-homing.yaml`
> (atom schema + dispositions), the cross-vendor ingest registry (6 of 7 providers live;
> grok is the one true vacuum), GITVS SEO + the inbound-magnet organ (surface layer), and
> FLAME.md + EVOCATOR (hydration manifest; "ninth organ" collides with rank 9 = Health).
> Precedent: `PREC-2026-08-06-external-charter-reconciles-before-adoption`.

# OPERATION PRIMA MATERIA
## System-Wide Healing Charter for meta-organvm

> This charter governs every agent session in this operation — Claude Code, Copilot, or any
> other instrument in the ensemble. Each agent hydrates from STATE.yml and the ninth organ,
> never from its own chat memory, and signs its work. Read it in full before acting.
> It supersedes any impulse to "just start fixing things." The operation is stateful, multi-week,
> and resumable — no single session completes it, and no session may act as if it could.

---

## 0. MISSION

The system — eight organizations, 148+ repositories, governed by ORGANVM; formerly and
fondly "{OS.me}", canonical name pending NAMES.md — has accumulated
years of debt: hundreds of open pull requests, hundreds of orphaned plans, thousands of
atoms scattered across repos, and thousands of AI conversations siloed inside every major
provider (Claude, ChatGPT, Gemini, Perplexity, Grok, OpenCode, and others). Repos duplicate
each other's functions. Chats contain unrouted decisions, designs, and drafts. No single
surface holds the whole.

The mission, in order:

1. **CENSUS** — see the whole system truthfully, from live state, with real numbers.
2. **CORPUS** — ingest every chat and every artifact from every provider into one
   indexed, Obsidian-openable, provenance-tagged body of work. Nothing lost.
3. **TRIAGE** — give every atom exactly one explicit disposition. Nothing left in limbo.
4. **CONSOLIDATE** — extract duplicated functions into canonical libraries; every repo
   knows what it is and points to what it depends on.
5. **SURFACE** — publish the distilled layer: SEO'd, discoverable, built for inbound.
6. **STEADY STATE** — a recurring heal ritual so debt never accumulates again.

The census output becomes the seed of the **ninth organ** — the canonical operator state
manifest already identified as the system's structural gap. Any agent instance hydrates
from it instead of from chat memory. This operation builds it.

---

## 1. PRIME DIRECTIVES

**D1 — NOTHING IS LOST; NOT EVERYTHING STAYS OPEN.**
Every atom receives exactly one disposition (§2). Closing with provenance is preservation,
not erasure. Open issues must equal intended work — a tracker where nothing closes is a
landfill with labels, and it destroys the contextual awareness this operation exists to
create. ARCHIVE is a first-class, dignified, indexed, permanently linkable fate.

**D2 — HYDRATE FROM LIVE STATE.** REMOTE_IS_CANONICAL. Enumerate orgs, repos, PRs,
issues, and branches via `gh` against GitHub itself. Never trust memory, prior chat
summaries, or stale local clones as a picture of the system.

**D3 — READ ORGANVM'S OWN TAXONOMY FIRST.** Before routing anything, read the meta-organvm
governance docs (stratvm rules: naming, semver, routing/labeling/containment). Atoms are
routed by what they ARE under the system's native ontology — not by ad-hoc categories
invented mid-session. If the taxonomy is ambiguous for an atom class, flag it as a
governance gap; do not improvise silently.

**D4 — READ-ONLY UNTIL APPROVED.** Phase 0 makes zero mutations. Every later phase mutates
only within an approved batch. Never force-push, never rewrite history, never delete
branches, repos, or files — deprecate and archive instead. Mutations to org repos go
through branches and PRs per GitHub best practice.

**D5 — BATCH CADENCE.** explore → plan → build → verify → heal, applied per batch of
25–50 atoms — never globally. Each batch ends with a digest for human approval before the
next begins. WIP cap: one batch in flight at a time.

**D6 — PROVENANCE IS SACRED.** Every atom carries frontmatter (§3): source provider,
origin id/URL, date, content hash. Every promoted issue links back to its source atom.
History is data.

**D7 — NEVER FABRICATE HISTORY.** Process only what exists on disk or on GitHub. If a
provider's export is missing or partial, inventory the gap and report it. Do not
reconstruct conversations from memory. Ever.

**D8 — IDEMPOTENT AND RESUMABLE.** All progress lives in `STATE.yml` and
`manifest.jsonl` in the operation repo. Dedupe by content hash. Any session, on any
machine (hot-cache doctrine: local is disposable), resumes by reading state — never by
asking "where were we?"

---

## 2. THE DISPOSITION SYSTEM

Every atom — chat, artifact, plan, orphaned PR, duplicate script, stray doc — gets
exactly one of five dispositions. "Pending" is a queue position, not a resting place.

| Disposition | Meaning | Destination |
|---|---|---|
| **PROMOTE** | Live intent to act. Becomes (or attaches to) a GitHub issue in its owning organ, with a link back to the source atom. | Owning repo's issue tracker |
| **MERGE** | Duplicate or variant of an existing canonical item. Recorded and cross-linked both ways; the canonical absorbs anything unique. | The canonical atom/issue |
| **EXTRACT** | Reusable code shared across repos. Moves to a canonical library repo; consumers pin semver; copies deprecated with a pointer. | Shared library organ/repo |
| **DISTILL** | Publication-worthy thought — essay seed, framework, artwork, position. Queued for the Phase 4 surface layer. | `corpvs/distill/` queue |
| **ARCHIVE** | Preserved verbatim, indexed, linkable, searchable. No work item. The default for pure exploration. Archive without guilt — this frees the mental space. | The corpus |

Rules:
- PROMOTE is expensive. It creates a standing obligation. The bar: *would Anthony schedule
  this in the next 90 days?* If not, it is DISTILL or ARCHIVE — both fully recoverable if
  intent returns.
- Orphaned PRs get the same treatment: merge, close-with-reason + link to a PROMOTEd
  successor issue, or convert to a draft issue and close. Zero PRs left ambiguous.
- A closed item with provenance can always be reopened. An open item with no intent can
  never be trusted. Optimize for a trustworthy tracker.

---

## 3. ATOM SCHEMA

One markdown file per atom. Plain markdown + YAML frontmatter + wiki-links so the corpus
opens directly as an Obsidian vault and imports cleanly to Notion.

```yaml
---
id: atom-<sha256-first8>
type: chat | artifact | plan | pr | script | essay | concept | decision
source: claude | claude-code | chatgpt | gemini | perplexity | grok | opencode | github | other
origin: <conversation id, URL, or repo#pr>
date: <original creation date, ISO>
title: <short descriptive title>
organ: <owning organization | unassigned>
disposition: pending | promote | merge | extract | distill | archive
promoted_to: <issue URL, if promoted>
relations:
  depends-on: []
  extends: []
  supersedes: []
  relates-to: []
tags: []
hash: <sha256 of body>
---
```

- Artifact extraction: any fenced code block, canvas, or artifact payload of ~30+ lines
  inside a chat becomes a **child atom** (`type: artifact`) linked to its parent chat atom.
- One atom = one thing. A chat covering four ideas may yield four concept atoms plus the
  parent chat atom. Connections come from links, not from cramming.

---

## 4. INTAKE PROTOCOL — THE CORPUS

Total scope: **every chat and every artifact from every provider ever used.** Claude Code
cannot reach other providers' servers; ANTHONY gathers exports into `_intake/`, and
sessions process only what is on disk.

```
corpvs/                      # proposed name — confirm/rename per stratvm naming protocol
├── _intake/                 # raw exports, untouched (gitignored or LFS as needed)
│   ├── claude/              # claude.ai data export (Settings → export; paths drift — verify)
│   ├── claude-code/         # local transcripts: ~/.claude/projects/**  (already on disk)
│   ├── chatgpt/             # ChatGPT data export (arrives by email as a zip)
│   ├── gemini/              # Google Takeout → Gemini Apps
│   ├── perplexity/          # account export or thread-by-thread capture
│   ├── grok/                # X/Twitter data archive (includes Grok) or Grok export
│   ├── opencode/            # local session logs
│   └── misc/                # anything else (Copilot, Cursor, etc.)
├── atoms/                   # normalized atoms (§3), organized <source>/<yyyy>/<id>.md
├── distill/                 # publication queue
├── indices/                 # by-nature, by-state, by-organ, by-source navigation hubs
├── manifest.jsonl           # one line per atom: id, hash, source, disposition, status
├── STATE.yml                # operation state: phase, current batch, counts, gaps
└── CHANGELOG.md             # Keep a Changelog format; dated corpus snapshots as tags
```

- ANTHONY'S STANDING TASK: request exports from every provider **today** — several take
  24–72 h to generate. Drop each in `_intake/<provider>/` untouched.
- Sessions begin intake work by inventorying `_intake/`: what is present, what is missing,
  what is partial. The gap report is a deliverable, not a failure (D7).
- Semver: org repos get releases per stratvm rules; the corpus gets dated snapshot tags
  and a running CHANGELOG.

---

## 5. PHASES

**PHASE 0 — CENSUS (read-only; the first session's entire job)**
1. `gh auth status`; enumerate all organizations and all repositories.
2. Read meta-organvm governance docs; load the native taxonomy and routing rules (D3).
3. Per repo, collect: open/stale PR count and ages, open issues, stale branches, last
   commit, README/CHANGELOG/license presence, default-branch protection.
4. Shallow-clone all repos; hash files to build a cross-repo duplication map (identical
   and near-identical scripts/functions clustered).
5. Inventory `_intake/` (whatever exports have landed) and local transcript sources.
6. Emit: `CENSUS.md` (the numbers — totals, top duplication clusters, oldest PRs, orphan
   counts), `NAMES.md` (canonical name registry: every name the system and its parts have
   carried, with status — current / superseded-by / retired-with-honor — and dates; names
   are atoms, supersession is a first-class relation, and beloved names are retired, never
   erased), `manifest.jsonl` seed, `STATE.yml`, and a **proposed batch plan** for Phases
   1–3.
7. STOP. Report. Await approval. This census is the first draft of the ninth organ.

**PHASE 1 — INTAKE NORMALIZATION.** Parse each provider export into atoms per §3.
Dedupe by hash. Extract child artifacts. Build indices. Verify the corpus opens as an
Obsidian vault. Report per-provider counts and gaps.

**PHASE 2 — TRIAGE AT SCALE.** Batches of 25–50 atoms through the disposition system.
Each batch: proposed dispositions table → Anthony approves/amends → execute (create
issues, cross-link, archive) → verify links resolve → heal (update manifest, indices,
STATE) → digest. PROMOTEd issues land in the owning organ with source-atom links.

**PHASE 3 — CODE CONSOLIDATION.** Work the duplication map: extract shared functions to
canonical library repos, version them, migrate consumers via PRs, deprecate copies with
pointers. Every repo gains a current README and status per curation standards.

**PHASE 4 — SURFACE.** Build the public layer from the DISTILL queue only: curated,
cross-linked, SEO'd. Inbound comes from the distilled layer — publishing raw corpus
buries the signal. Profile READMEs, pinned repos, topics, and the portfolio surface get
aligned here.

**PHASE 5 — STEADY STATE.** A weekly heal ritual (30–60 min): process new chats into
atoms, triage the week's batch, update the ninth organ, snapshot the corpus. Debt is
paid weekly or it compounds.

---

## 6. BATCH DIGEST FORMAT

Every batch and every phase ends with a digest, appended to `STATE.yml` history:

```
BATCH <n> — <phase> — <date> — agent: <claude-code | copilot | ...>
Processed: <count> atoms | Promoted: n | Merged: n | Extracted: n | Distilled: n | Archived: n
Issues created: <links>   PRs opened/closed: <links>
Gaps/anomalies: <list>
Governance questions for Anthony: <list>
Next batch proposal: <summary>
```

---

## 7. DEFINITION OF HEALED

- [ ] Every provider's export ingested or its gap explicitly documented.
- [ ] Every atom in the manifest carries a non-pending disposition.
- [ ] Zero open PRs older than 30 days without an explicit disposition.
- [ ] Open issues = intended work; everything else archived with provenance.
- [ ] Duplication clusters resolved into versioned canonical libraries.
- [ ] Every repo: README, status, topics, semver releases per stratvm.
- [ ] Corpus opens as an Obsidian vault; indices navigate by nature, state, organ, source.
- [ ] The ninth organ exists and is the single hydration source for any agent instance.
- [ ] NAMES.md is canonical: every current name governed by stratvm, every former name
      recorded with its era.
- [ ] The distilled surface layer is live and discoverable.
- [ ] The weekly heal ritual has run at least twice.

---

## 8. BOOTSTRAP — BEGIN NOW

You are in **Phase 0**. Do not skip ahead. Do not mutate anything.

1. Confirm `gh` auth and enumerate every organization and repository you can see.
2. Read meta-organvm's governance documentation before classifying anything.
3. Execute Phase 0 steps 1–6 above.
4. If the `corpvs` repo does not exist, propose its creation (name subject to stratvm
   naming protocol) — but create nothing until the census is approved.
5. Deliver `CENSUS.md` and the proposed batch plan. Then stop and report.

Explore. Plan. Build. Verify. Heal. Repeat — one batch at a time, until the whole
system is prima materia: not everything completed, but everything *decided*, everything
placed, everything findable, and nothing hanging over anyone's head.
