# dustin alpha→omega: research, atomize, semver, roadmap, and issue all three ventures

Issue: #2362
PR: (pending)

## Context

The three dustin venture repos (`4444J99/post-dsp-platform`, `4444J99/the-consulate`,
`4444J99/new-ancients-social`) hold working stage-1 code (59/66/38 tests) and zero planning
surface: 0 issues, 0 milestones, 0 tags, default labels only. The operator directive
(2026-08-13): all projects researched, annotated, brainstorms atomized and semver'd, then all
phases alpha→omega planned root-to-leaf and materialized as GitHub issues. This plan is the
executable decomposition of that directive. Scope is the three dustin lanes; the pipeline
generalizes to other constellation lanes if the operator widens scope later.

## Resolved design decisions

1. **Machine-read roadmap data is JSON, not YAML** — the venture repos are zero-dependency
   Node 22 and gain no YAML parser. Binds: `scripts/dustin-alpha-omega-done.sh` (predicate,
   ships with this task's register PR), which asserts each repo's `roadmap/*.json` validates
   via that repo's own `check-roadmap.js`.
2. **Atom vocabulary is limen's eight kinds** (projects-to-start, decisions, tasks, vacuums,
   questions-unresolved, client-offerings, schema-proposals, functionality-to-repeat) — binds:
   `institutio/governance/atom-homing.yaml`; atoms are minted directly into each repo's
   `roadmap/atoms.json`, never through `scripts/brainstorm-harvest.py` (its store is keyed by
   CCE corpus threads, which these sources are not).
3. **`scripts/constellation-dossier.py --write` is not run for slug dustin** — it would
   overwrite three hand-consolidated private dossiers with keyword-excerpt skeletons swept from
   the wrong corpora. Public dossier halves are curated partner-safe extracts landed in each
   venture repo, scanned by that repo's hashed redaction denylist. Binds:
   `scripts/constellation-dossier.py` (dry-run only), `roadmap/redaction-denylist.json` per repo.
4. **Register `dossier:` fields point at limen-tracked pointer files** under
   `organs/consulting/constellation/dossiers/` — `validate-constellation.py` Rule #4 requires a
   path that exists from the limen repo root, so a `repo::path` string would mint a fresh
   violation. The pointer file names the venture repo + path and holds no corpus content.
   Binds: `organs/consulting/constellation/validate-constellation.py:176`.
5. **Partner-safety is a predicate, not a habit** — `publication-policy.py` is owner-scoped
   (its own source: third-party identifiers "stay unadjudicated"), so each venture repo carries
   a SHA-256 hashed n-gram denylist and an offline scanner that fails on any match, reporting
   class, never token. Binds: `scripts/publication-policy.py`, per-repo check I.
6. **Phases are GitHub milestones; epics and leaves are issues** with HTML identity markers
   (`<!-- roadmap:<node-id> -->`) in bodies, created from committed body files by plain `gh`
   calls with per-pass caps and pacing; reconcile receipts assert planned==created by marker
   set comparison, never by count. Binds: `scripts/sync-censor-issues.py` (identity pattern),
   `scripts/positioning-program.py` (two-pass link resolution), per-repo
   `roadmap/receipts/reconcile-*.json`.
7. **Human-gated phases are planned, never started** — five levers minted in
   `his-hand-levers.json` (`L-DUSTIN-GH-PROFILE`, `L-DSP-TEN-QUESTIONS`, `L-CONS-PRICE`,
   `L-NAS-TERMS`, `L-NAS-CREDENTIALS`); gated nodes carry `gated:human` and a lever id; the
   per-repo validator fails any phase that is neither done nor carrying a recorded deferral.
   Omega (v1.0.0) is not hostage to unanswered questions: deferral blocks are explicit,
   operator-decided records. Binds: `his-hand-levers.json`, per-repo check G.
8. **Fable compliance**: acceptance receipt written before execution
   (`logs/fable-acceptance/20260813T051013Z-dustin-alpha-omega-roadmaps.json`, category
   governance, 10%); synthesis stays in the session; research, file materialization, and bulk
   issue creation are delegated to explicitly tiered sonnet/haiku agents executing committed
   manifests. Binds: `docs/fable-allotment.md`, `scripts/fable-allotment.py`.
9. **The pre-existing `constellation-registry` red is pinned as an exact string**
   (Rule #6, 12 public-only slugs) — any validator output differing from the pinned baseline
   is a fresh regression owned by this work. Binds: `scripts/dustin-alpha-omega-done.sh`
   (predicate, ships with this task's register PR), which embeds the pinned violation line
   and fails on any non-identical validator output.

## Steps

1. Research: three web landscape briefs (post-DSP market, higher-ed AI audit practice,
   release-cycle marketing norms) written into each repo's `docs/research/landscape-2026.md`;
   the 8-doc Drive corpus consolidated into `post-dsp-platform/docs/research/drive-corpus/`;
   venture specs extracted from the private tape (product content only, redaction rules
   enforced) into `docs/research/original-spec.md` / `original-concept-note.md`;
   dossier extracts per repo.
2. Atomize: per repo, candidate atoms mined from every research/spec/dossier/README source
   (sonnet miners), curated and milestone-assigned in-session, landed as `roadmap/atoms.json`
   + `roadmap/sources.json` + `roadmap/findings.json`.
3. Ladder: per repo `roadmap/ladder.json` — 10-11 phases alpha→omega mapped to semver
   (v0.1.0 alpha = shipped baseline … v1.0.0 omega), epics and leaves with runnable acceptance
   predicates; `ROADMAP.md`, `docs/research/RESEARCH.md`, `SOURCES.md`, `QUESTIONS.md`,
   `CONTRADICTIONS.md` generated/authored; `bin/gen-roadmap.js`, `bin/check-roadmap.js`,
   `bin/gen-gh-plan.js`, `bin/reconcile-issues.js`, `src/roadmap-check.js` + node --test
   wrapper. Tag v0.1.0 on the shipped baseline commit; push.
4. Materialize: labels, milestones, then issues (epics + leaves, ~372 across the three repos)
   from committed body files, paced, capped per pass, repo by repo; reconcile to PARITY;
   pass 2 rewrites child references to real issue numbers where body hashes changed.
5. Limen registration: register `dossier:` pointer files + notes, five levers, derive-streams
   regeneration, remediation issue for the pre-existing engagement-record exposure; memory
   files for the two session lessons (clones are not the durable copy; worktree switches kill
   in-flight subagent shells).
6. Closeout: done predicate (sets not counts; artifacts read from HEAD; pinned red compared
   byte-exact), session-plan close, terminal statement.

## Premortem

- The dossier tool's `--write` would have destroyed three hand-authored dossiers — caught in
  design; encoded as decision 3. Anything else that "regenerates" must be diffed before run.
- Venture clones vanished twice this week; GitHub is the copy of record. Every write stage
  re-probes `git -C <abs> rev-parse HEAD` against the remote before writing.
- GitHub secondary rate limits (~20 content-creates/min) make ~840 mutations a paced,
  multi-sitting batch — the committed manifests make every pass replayable.
- The pinned pre-existing red could mask a fresh violation if compared loosely — byte-exact
  comparison only.
- 372 issues land in repos the partner cannot yet see (no GitHub profile — DUS-003). The
  lever is minted and ordered first; the roadmap does not wait on it.

## Verification

- Per repo: `node bin/check-roadmap.js` green (schema, id grammar, homing, dependency closure,
  semver monotonicity, predicate presence, gate bidirectionality, generated-artifact byte
  identity, denylist scan, receipt parity); `npm test` green including the roadmap test;
  reconcile receipt verdict PARITY; tag `v0.1.0` on origin.
- Limen: `bash scripts/verify-scoped.sh` green on each PR branch; `merge-policy.sh` CLEARED
  before merge; `python3 scripts/session-plan.py audit` shows no GAP for this slug;
  `python3 organs/consulting/constellation/derive-streams.py --check` parity;
  constellation validator output byte-identical to the pinned pre-existing red.
