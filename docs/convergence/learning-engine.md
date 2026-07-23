# Learning-Engine Convergence — one owner per capability

**Decided 2026-07-23.** Status: **canonical** (this record is the authority; do not build a new
learning/study/syllabus/interview-prep engine — extend the owners named here).

## Why this exists

The operator has built adaptive-learning / syllabus / study systems **~6 times**. An excavation of the
repos *and* the AI-chat / brainstorm / iOS-note archives (4 explorers, 2026-07-23) found the same ~8
capabilities re-invented 3–5× each, and a **canonical design that already exists and was twice
peer-critiqued**. A 7th (`agon`, greenfield ASI interview prep) was started and caught. This record
converges them: **name one owner per capability; everything else is a subject/tenant, a plugin, or a
surface.** "Do it right, do it once."

## The canonical design (read before proposing changes)

- **`os-syllabus-v3.md`** — the operator's Adaptive Personal Syllabus design, hybrid practice
  (engineering + myth + rhetoric + growth). Path: `edu-organism-…/skins/homeschool/adaptive-personal-syllabus/docs/syllabusEVOLUTION/os-syllabus-v3.md`.
- **`syllabus_critiques_synthesis.md`** — GROK + Claude critiques already synthesized (the fix-list).
  Path: `~/Workspace/session-meta/data/session-transcripts/chatgpt-export-2026-04/`.
- **Pedagogy primitives that MUST be honored** (not overridden): personalization-first; **Wings**
  (8 artifacts/unit: Academic/SOP/Business/Social/Community/Wiki/Web/Grants); constructionist /
  project-as-teacher; cross-disciplinary tie-ins; **ChainBlockARK** provenance ledger; quality gates
  (completeness / personalization ≥60% / provenance / cross-ref); wave cycles (generate→review→refine);
  the 5-persona multi-archetype critique; the evaluation→growth feedback flow; the Studio-Quest
  milestone ladder.

## One owner per capability

| Capability | **Owner** | Path | Notes |
|-----------|-----------|------|-------|
| Curriculum + personalization | **Adaptive Personal Syllabus (`aps` / `syllabus` CLI)** | `edu-organism-…/skins/homeschool/adaptive-personal-syllabus` | v0.6.0, tested, ACTIVE. Produces personalized `learning_path`; `PersonalizedLesson` schema; ChainBlockARK `ledger.py`. `community-hub/syllabus.py` is its web surface. |
| Daily cadence (compose→check→render→log→gate) | **daily-engine** | `~/Workspace/daily-engine` | Deterministic, 17 invariant checks, journaled `revisions.jsonl`, readiness + evidence gates. The cadence spine. |
| Interview content (STAR ×9 identities, org intel, gap analysis) | **application-pipeline/interview_prep.py** | `~/Workspace/application-pipeline` | The STAR-bank owner. Do NOT re-author STARs elsewhere. |
| Content atoms (hybrid search) | **my-knowledge-base** | `~/Workspace/organvm/my-knowledge-base` | 548 atoms; future content source for lessons. |
| Reward surface (XP / levels / achievements / streaks) | **gamified-coach-interface** | `~/Workspace/gamified-coach-interface` | Live on Pages. Optional delivery/reward layer. |
| Spaced repetition (review intervals) | **agon** (only this) | `_matters-private/job-asi-algora/agon` | The one capability none of the above had. Everything else in agon was retired. |
| Multi-medium canon (reading + handwriting + music + film) | **studium** | `~/Workspace/limen/studium` | Its own subject; shares the cadence + ledger pattern. |

## Disposition of every prior build

- **Adaptive Personal Syllabus** → **ENGINE** (curriculum + personalization owner). Canonical.
- **daily-engine** → **cadence spine** (owner). Do not fork; lift its generic core in Phase 2.
- **application-pipeline/interview_prep.py** → **interview-content owner**. Reuse.
- **community-hub/syllabus.py** → **web surface of `aps`** (same organ). Keep.
- **gamified-coach-interface** → **reward surface** (Phase 2 wire-in).
- **my-knowledge-base** → **content-atom source** (Phase 2 feed).
- **studium** → **a subject** of the same spine (parallel tenant).
- **edu-organism** → institutional kernel/skins; the `aps` engine lives inside it.
- **RE:GE OS Curriculum v2** → superseded by os-syllabus-v3 (was in `.Trash`). Historical.
- **`agon`** → **RETIRED as an engine; kept as a thin tenant** — the ASI-interview subject +
  the spaced-rep plugin. Its greenfield `curriculum.yaml` was deleted; curriculum is now
  `PersonalizedLesson` records in the `aps` schema; provenance is a ChainBlockARK ledger.

## The subject/cartridge contract

A subject is a set of **`aps` `PersonalizedLesson` records** (schema:
`adaptive_personal_syllabus/lesson_schema.py`): `{lesson_id, title, learner_name, source, source_concept,
why_this_matters, personalized_translation, repo_task, evidence{items}, next_command, context}` plus an
`aps` `LearnerProfile`. First conforming subject: **ASI FSE interview prep** (`_matters-private/job-asi-algora/agon/lessons.json`).
New subjects author lessons in this schema — they do NOT invent a new curriculum format.

## Known blocker — RESOLVED 2026-07-23 (organvm/edu-organism#52, merged)

`aps` used to die at import on `koinonia_db.constants.ORGAN_MAP` (the private `koinonia-db` organ
package is absent — `organvm-vi-koinonia` is empty here). **Fixed by making koinonia-db an optional
backend, not removing it:** the import is guarded with an `ORGAN_MAP = {}` fallback (a non-organ
subject's own slugs then pass straight through), `koinonia-db` moved from a hard dependency to an
optional `[koinonia]` extra, and the organ-backend tests skip when it is absent (run unchanged when
present). Result: `aps` installs, boots, and passes 34/34 non-backend tests standalone.

So the ASI subject is now **generated by `aps`**, not merely schema-conformant: an aps taxonomy seed
(`_matters-private/job-asi-algora/agon/aps/seed/{taxonomy,reading_lists}.json`) + an `aps`
`LearnerProfile` (`profile.json`) run through `aps corpus ingest` → `aps plan generate`, emitting
`asi-learning-path.{md,json}` (12 modules, ~24 h) with the aps ledger INTACT. The empty-`ORGAN_MAP`
fallback **is** the "subject pluggable" decoupling — any non-organ subject runs through `aps` directly.
(Full `koinonia-db` restoration for organ subjects remains a separate, optional Phase-2 item.)

## Phase 2 (separate approval) — the full lift

Lift daily-engine's domain-generic core out of `_health-private` into a shared substrate; make fitness,
asi-interview, and studium-canon all subjects of `aps` + daily-engine; decouple `aps` from the organ
taxonomy; wire the gamified-coach reward surface + my-knowledge-base content feed; implement the
`syllabus_critiques_synthesis` fixes (embedded assessment metrics, inter-unit data flow, ChainBlockARK
generalized). Convergence-by-lifting existing code — never greenfield.

## Rule

Before building ANY learning/study/curriculum system: read this record, pick the owner, extend it.
A new engine is a regression. See also `docs/IDEAL-FORMS-LEDGER.md` → IF-LEARNING-ENGINE.
