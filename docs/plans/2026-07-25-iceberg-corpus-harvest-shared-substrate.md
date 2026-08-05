# Sorting the iceberg — corpus unity, brainstorm harvest, and shared substrate

## Context

The operator asked for three things: find the AI-chat brainstorm sessions ("there are a lot of
them"), give each its own state with repositories where none exist, and work out what machinery
should be shared between front-end surfaces and back-end engines — plus proper research on the
education estate, "because we've built up a lot."

Exploration measured it. The tip was smaller than assumed and the problem is different from the
framing.

**The corpus**

- `~/Workspace/session-meta` — 3.5 GB raw transcripts (2,627 Claude sessions, 571 Codex rollouts,
  ChatGPT/Gemini/Copilot/browser exports), already atomized to a 1.36 GB `atoms.jsonl` with its own
  redaction pipeline and per-provider adapters.
- `~/Workspace/_conversations-private` — 371 MB / 1,177 files; ~107 ChatGPT + ~426 Claude + 20
  Perplexity threads plus cross-provider federation indexes. Local-only, no remote, registered as
  the CCE corpus-store root.
- `organvm/brainstorm-20260423` — the precedent: **24 conversations → 934 atoms**, including **149
  `projects-to-start`**. One export date. Self-described as *"canonical staging for downstream
  personae-registry / IRF atoms / repo seeds."*

**Three findings that reframe the work**

1. **The only splitter is broken.** `scripts/constellation-dossier.py` resolves its corpus home to
   `~/Workspace/limen` (no corpora there) instead of `_conversations-private`, and imports CCE from
   a nested path that does not exist — the checkout is a *sibling* named `conversation-corpus-check`.
   Running it yields `no populated corpus`. `organs/consulting/constellation/check.py` carries the
   identical bug. The brainstorm→project pipeline currently moves nothing.
2. **Two ingestion systems that do not talk.** CCE (curated) and session-meta (exhaustive) have
   separate schemas, redaction, and manifests. Anything living only in session-meta is invisible to
   every downstream consumer.
3. **Zero code sharing across ~310 repos.** No submodules, no internal packages, no template repo.
   The six Cloudflare Worker micro-SaaS repos each reimplement Stripe/auth/rate-limiting inline in a
   single `index.ts`. There is no repo-scaffolding path at all — `gh repo create` appears twice in
   the codebase, both one-offs; the estate is governed *after* creation via `estate.yaml`.

**Why this shape and not "mint 149 repos"**

`docs/IDEAL-FORMS-LEDGER.md` → **IF-AMALGAMATION** records the fleet's distance as *"75 open PRs,
157 unmerged branches; duplicates accrete faster than they merge,"* against an ideal where the fleet
amalgamates faster than it spawns. Mass repo creation is a regression against a declared ideal.
**IF-LEARNING-ENGINE** supplies the replacement unit — its subject/cartridge contract, where a new
thing is *records in an existing schema*, never a new engine. So **a brainstorm-derived project is
an atom in a registry; a repo is minted only when an atom needs what only a repo provides** (its own
deploy surface, collaborator grant, or visibility boundary). Visibility is not a new decision
either: **IF-PUBLICATION-ESTATE** plus `estate.yaml` glob classes already own it.

This contradicts the literal ask ("there should be repositories, and in those repositories there
should be those brainstorm sessions"). Phase 5 builds the mechanism that mints them — gated by a
predicate rather than by hand. **The gate is a flag, not a fork:** open it and it mints broadly.

**Outcome:** every brainstorm session becomes addressable, every capability gets exactly one owner,
and repositories get minted by a predicate.

---

## Phase 0 — Repair the harvest path (~1h, unblocks everything)

- `scripts/constellation-dossier.py` — `_corpus_home()` returns `<live_root>/source-drop`'s parent
  (= `~/Workspace/limen`). Point it at the registered store root, read from a declared parameter
  (Phase 1), not a hardcoded path.
- Same fix in `organs/consulting/constellation/check.py` → `check_corpus_refresh()`.
- CCE import: both scripts `sys.path.insert` a nested `conversation-corpus-check/src`. Resolve the
  sibling checkout or prefer an installed `conversation_corpus_engine`. Reconcile the
  repo-name/dir-name drift (`conversation-corpus-engine` vs `conversation-corpus-check`), which also
  appears in `scripts/session-corpus-ledger.py`'s `ORGANS` table.
- **Done:** `scripts/constellation-dossier.py --all` emits non-empty dossiers instead of
  `no populated corpus`.

## Phase 1 — IF-CORPUS-UNITY: declare the corpora (registry, not migration)

Do **not** merge 3.5 GB into 371 MB. Declare both and make them addressable, using the estate's own
registry idiom (`gates.yaml` / `sensors.yaml` / `parameters.yaml`).

- New `institutio/governance/corpora.yaml`: `schema_version`, header naming every consumer,
  `owner:` + `note:` required per row, a `ratchets:` block for consumers as they convert. Rows carry
  corpus id, provider, root, format, adapter, freshness, redaction status.
- Rows for: the three CCE corpora, session-meta's archive + `atoms.jsonl`, `brainstorm-20260423`,
  and the five declared-but-unpopulated providers (gemini/grok/copilot/deepseek/mistral) as
  explicit `populated: false` — an empty provider is a counted vacuum, not an absence.
- Declare the corpus-root parameter in `institutio/governance/parameters.yaml` with `owner:`/`note:`
  so Phase 0 reads declared data.
- `scripts/check-corpora.py` — parity predicate, lettered checks in house style: (A) schema valid,
  (B) every declared root exists, (C) freshness re-derived from disk, (D) consumers derive rather
  than hardcode, (E) nothing declared-but-unreachable. Register it in `gates.yaml`; `check-gates.py`
  enforces the registration.
- **Reuse:** `scripts/session-corpus-ledger.py` already inventories local sources — make it a
  *consumer* of `corpora.yaml`, not a second source of truth.

## Phase 2 — IF-BRAINSTORM-HARVEST: generalize the extractor

`organvm/brainstorm-20260423/tools/synthesize.py` already produces the target shape
(`conversations/<stream>/NN-topic.md`, `atoms/*.yaml`, `streams/`, `entities/`, `schemas/`,
`cross-refs/`, `raw-source/` audits) but is hardcoded to
`DOWNLOAD_ROOT = /Users/4jp/Downloads/brainstorm-export-20260423`.

**Convergence-by-lifting, never greenfield** — the learning-engine doc's own rule.

- Lift it into `organs/consulting/constellation/` as a tool taking *any* corpus id from
  `corpora.yaml` and emitting the same artifact shape.
- Preserve its contract verbatim: the no-reduction extraction mandate, `protocol.yaml` + `seed.yaml`,
  and the eight atom kinds (`projects-to-start`, `decisions`, `tasks`, `vacuums`,
  `questions-unresolved`, `client-offerings`, `schema-proposals`, `functionality-to-repeat`).
- Stream assignment must be **derived**, not hand-authored. Reuse the shipped, tuned clustering in
  `organs/consulting/constellation/constellation-streams.py` → `find_echoes()` (IDF over
  name+description, `ECHO_FLOOR`, 2-core pruning) rather than writing a second clusterer.
- **Deterministic and idempotent** — re-running over an unchanged corpus is byte-identical. Every
  tie-prone sort must be total; `constellation-streams.py` shipped a real hash-order bug here.
- **Done:** re-running over `brainstorm-20260423`'s source reproduces its 934 atoms exactly; then
  the CCE ChatGPT + Claude corpora yield atoms for all ~530 threads.

## Phase 3 — One atom registry, not many repos

- Atoms land in the **private** store (`_conversations-private/` or `brainstorm-*` corpus repos) —
  never the public `limen` tree. They carry unfiltered thinking, client names, money talk.
- Cross-link into the **four existing** work registries rather than inventing a fifth — the
  reliquary's `reference_work_registries.md` names atoms/plans/IRF/pipeline with **IRF canonical for
  "what needs doing."** A `projects-to-start` atom becomes an IRF item, not a new board.
- Harvested project atoms matching an existing person's stream become **candidate lanes**, surfaced
  on the already-shipped Streams page under "unclaimed" — evidence for the demand review, never
  auto-registration.

## Phase 4 — IF-SHARED-SUBSTRATE: convergence as a registry, not essays

`docs/convergence/learning-engine.md` is the proven template (*one owner per capability*,
*disposition of every prior build*, *the cartridge contract*, *Phase 2*, *Rule*). It exists once.
Promote the method to declared data.

- New `institutio/governance/convergence.yaml`: one row per capability — `capability`, `owner` (the
  single implementation), `path`, `tenants`, `retired` (what it supersedes), `owner:`/`note:`.
- `scripts/check-convergence.py` makes *"never build the 7th"* executable: **red when a second
  implementation of an owned capability appears.** Use the ratchet + baseline pattern
  (`undeclared-params-baseline.txt` is the model) so existing duplication grandfathers in and
  shrinks, rather than breaking the build on day one.
- Seed rows from what is already decided plus what exploration found:
  - **learning-engine** — transcribe the existing capability table. **Fix a defect while doing so:**
    the doc points `aps` at `edu-organism/skins/homeschool/adaptive-personal-syllabus`, which is a
    read-only *mirror*; the canonical repo is `organvm/adaptive-personal-syllabus`. The owner must
    name the canonical.
  - **worker-toolkit** — the sharpest measured duplication: six Workers hand-rolling Stripe/auth/
    rate-limiting with zero runtime deps between them. Extract one package, convert one Worker as
    proof, ratchet the rest.
  - **text-quality scoring** — four independent encodings of "grade/score writing": `writelens`
    (live, billed, rate-limited — the most production-hardened, so the natural owner),
    `edu-organism/kernel/standards/*.json`, `editorial-standards/schemas/`,
    `essay-pipeline/validator.py`.
  - **rubric schema** — one canonical schema + registry; currently encoded three ways.
  - **data-export** — `data_export.py` is near-identical across `adaptive-personal-syllabus`,
    `community-hub`, and `reading-group-curriculum`.
  - **voice** — `vox` already exists as shared voice infrastructure ("clone, synthesize, transcribe,
    FastAPI"); neither `speech-score-engine` nor `sign-signal--voice-synth` calls it. Point both at
    `vox`; pick one as owner (`sign-signal--voice-synth` has working code, `speech-score-engine` has
    the better layout but is an admitted scaffold) and retire the other to a tenant.
  - **auditor** — `growth-auditor`, `organvm-scrutator`, `laurea`, `vulnpulse`/`cve-watch`/
    `bountyscope` all implement "score a thing against criteria, emit a verdict."
- Add **IF-SHARED-SUBSTRATE** to `docs/IDEAL-FORMS-LEDGER.md` with the measured distance (zero
  cross-repo dependencies across 310 repos).

### Education specifics (extend the existing doc — never author a second one)

`docs/convergence/learning-engine.md` names owners for 7 capabilities but predates the estate sweep.
Add a disposition for each repo it omits: `writelens`, `essay-pipeline`, `classroom-rpg-aetheria`,
`reading-observatory`, `reading-group-curriculum`, `laurea`, `composition-1-2`,
`editorial-standards`, `speech-score-engine`, `sign-signal--voice-synth`, `learning-resources`,
`community-hub`, `studium-generale`, `academic-publication`. Findings to encode:

- **`community-hub` is the single real front end** (live on Render) for curricula/syllabus/reading
  content produced by 3–4 back-end repos, each with its own export format. That is the front/back
  split the operator asked about, and the export-format divergence is the concrete tax.
- **`edu-organism` mirrors six standalone repos near-1:1** by design (read-only, `--squash`), but
  drift is caught only by a manual `verify.sh`, never CI. Encode the mirror direction as declared
  data so drift becomes a predicate.
- **Two `studium-generale` repos**: `organvm/studium-generale` self-declares superseded (2026-03-19)
  yet is unflagged on GitHub and still receives pushes; `studium-generale--4444j99` is the active
  one. Archive-flag the stale one so search stops landing on it.
- **`laurea` is mis-clustered** — a developer-portfolio metrics tool in academic branding; its topics
  are `developer-metrics`/`github-stats`. It belongs in the **auditor** row, not education.
- Then **execute learning-engine Phase 2**: lift daily-engine's generic core into a shared substrate,
  decouple `aps` from the organ taxonomy, wire the reward surface + KB feed.

## Phase 5 — IF-REPO-GENESIS: mint repos by predicate

Last and smallest. There is no scaffolding path today; build the gated one.

- `scripts/repo-genesis.py`: given an atom id, mint **only if** the gate passes — demand evidence
  (review-before-rails), a name cleared by `scripts/nomenclator.py --check`, and an `estate.yaml`
  class that resolves (never class `J`).
- On mint it performs the whole registration in one motion, since nothing does this today: create
  the repo, seed it with the brainstorm sessions that produced it plus a `seed.yaml`, add the
  `estate.yaml` `repo_overrides` row (required `why:`) via `gitvs.py classify --emit-overrides`, and
  open a PR — rows land by PR, never auto-written.
- Visibility is **not** a parameter of this tool; `estate.yaml` globs assign the class.
- Add **IF-REPO-GENESIS** to the ledger.

---

## Verification

```bash
# Phase 0 — the splitter moves material again
scripts/constellation-dossier.py --all                  # non-empty; no "no populated corpus"

# Phase 1 — corpora declared and reachable
python3 scripts/check-corpora.py                        # exit 0; checks A-E
python3 scripts/check-gates.py                          # new gate registered, no drift

# Phase 2 — reproduces the precedent, then scales, then repeats identically
<harvest> --corpus brainstorm-20260423 --verify         # reproduces 934 atoms exactly
<harvest> --corpus chatgpt-local-session-memory         # atoms for ~107 threads
<harvest> --corpus chatgpt-local-session-memory         # re-run: byte-identical

# Phase 4 — the anti-duplication predicate
python3 scripts/check-convergence.py                    # red on a 2nd impl of an owned capability
cd <converted-worker> && npm test                       # proof-of-extraction Worker still green

# Phase 5 — genesis is gated
scripts/repo-genesis.py --atom <id> --dry-run           # refuses without demand evidence
python3 scripts/nomenclator.py                          # roll valid
python3 scripts/gitvs.py doctor                         # no class J; drift == 0

# Before any merge
scripts/verify-scoped.sh                                # the default push gate
```

**Privacy invariants, each with a shipped enforcement point — non-negotiable:**

- Harvested atoms and raw brainstorm content never enter the public `limen` tree.
- `composition-1-2` is **FERPA-flagged student data** — it is deliberately excluded from
  `edu-organism` absorption pending a scrub. No phase may ingest it into a shared corpus.
- The constellation register's Rule #2 (no surnames) stays green — `validate-constellation.py`.
- `scripts/publication-policy.py redact --apply` gates any public dossier half; a redaction failure
  deletes the public file and fails the run. Preserve that behavior.
- The shipped `publish-constellation.py` leak gate stays in force: no private repo name reaches a
  hosted page unless GitHub already serves it publicly.
