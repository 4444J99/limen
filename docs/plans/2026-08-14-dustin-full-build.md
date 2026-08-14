# dustin full build: execute the alpha→omega machine runway (18 phases, 202 leaves)

Issue: #2390
PR: (pending)

## Context

The three dustin venture repos carry fully-issued alpha→omega roadmaps (plan
`docs/plans/2026-08-13-dustin-alpha-omega-roadmaps.md`, issue #2362, PR #2364) but zero
implementation beyond the shipped v0.1.0 alphas: every P02+ acceptance command references code
that does not exist yet (~32 new test files, ~20 new CLIs, ~15 modules, 4 fixture sets). The
operator directive (2026-08-14): **plan the full build** — the entire ungated machine runway,
driven to phase predicates, with the human-gated frontier untouched:

| repo | runway | leaves | topology |
|---|---|---|---|
| post-dsp-platform | DSP-P02..P08 | 102 (13/14/13/17/14/17/14) | strict chain |
| the-consulate | CONS-P02..P06 | 46 (10/9/9/9/9) | strict chain; P08/P09 wait on gated P07 by declared `depends_on` |
| new-ancients-social | NAS-P02..P07 | 54 (10/9/10/9/8/8) | diamond: P02→P03 ∥ P04 ∥ P05 ∥ P06 → join P07 |

Ground truth (three-repo exploration, 2026-08-14): completion status is hand-edited in
`roadmap/ladder.json` and the validator forces an **atomic completion pass** — any ladder edit
breaks check H (byte-identity) until `bin/gen-roadmap.js` reruns, breaks check J (issue-map pins
the ladder SHA) until a fresh reconcile lands, check E ties `package.json` to the last done
phase, and reconcile `state_mismatch` requires ladder-done ↔ issue-closed agreement.
`--phase-proof` is a consistency guard on a done-claim, not a completion gate; `--phase-done` is
the binary read. Gated levers #2367–#2371 stay untouched; check G enforces planned-never-started.

## Resolved design decisions

- **D1 — the atomic per-phase completion pass** (beat "flip statuses as leaves land", which
  breaks H/J on every interim commit): close the phase's leaf+epic issues (paced, sleep 3) →
  flip leaf/epic/phase + same-milestone atom statuses to done → bump `package.json` to the phase
  version → `node bin/gen-roadmap.js` → capture `gh issue list` re-serialized through the
  engine's canonicalJSON (check A walks receipts) → `bin/reconcile-issues.js` to fresh PARITY →
  full `npm test` + `bin/check-roadmap.js` + `--phase-done <id>` true, exit codes read bare →
  one commit → tag `vX.Y.0` → push with tag → close the GitHub milestone. Binds:
  `scripts/dustin-build-done.sh` (ships as this plan's implementing PR).
- **D2 — leaf implementation commits never touch `roadmap/`**; ladder mutations happen only in
  completion passes and phase-start amendment micro-passes, so `npm test` stays green on every
  interim commit. Binds: `scripts/dustin-build-done.sh`.
- **D3 — the CONS deliverable renderer lands at `src/deliverable.js`**, never at the literal
  `src/render.js` its leaf statement names — that path is the roadmap engine's render layer
  (consumed by check H; copied byte-for-byte across the three repos). Amendment micro-pass at
  CONS-P03 start: edit the leaf statement → regen → `gh issue edit` the one changed body →
  reconcile → commit. Binds: `scripts/dustin-build-done.sh`.
- **D4 — NAS-P05 gains a `gated:human` corpus-import leaf at P05 start** (mirroring
  NAS-P02-E02-L02): without it the phase can go "done" on a synthetic scaffold while its exit
  gate claims "voice corpus built from his own material". The import waits on the partner;
  the scaffold leaves do not. Binds: `scripts/dustin-build-done.sh`.
- **D5 — phases complete in version order per repo** (contiguous done prefix): NAS's diamond
  legs may BUILD in parallel, but ladder flips + version bumps + tags land in semver order, so
  check E's "last done phase" is always well-defined. Binds: `scripts/dustin-build-done.sh`
  (frontier check asserts contiguity).
- **D6 — direct-main, conventional commits, no issue refs in subjects (the repos' own
  convention), push at least once per epic** — GitHub is the copy of record; the clones have
  vanished twice. Binds: `PREC-2026-08-13-clones-are-not-the-durable-copy`.
- **D7 — tiering: sonnet builder agents per epic; opus design review only before the flagged
  hard completions** (DSP-P02 event-log schema, DSP-P05 statement ingest, DSP-P06
  API+entitlement kernel, CONS-P03 deliverable engine, NAS-P03 attribution model); the session
  conducts and writes a fresh Fable acceptance receipt per orchestration sitting before build
  work starts. Binds: `scripts/fable-allotment.py`.
- **D8 — at most 3 concurrent build lanes (one per repo)** on the 16GB host; untiered/expensive
  fan-out is audited every session. Binds: `scripts/claude-workflow-guard.py`.

## Steps

1. Ship `scripts/dustin-build-done.sh` — the executable definition of done, before the work
   (this plan's implementing PR). Default mode: exit 0 ⟺ build state COHERENT (per repo: done
   prefix contiguous from P01; every done phase has `--phase-done` true, origin tag, closed
   milestone, fresh PARITY receipt, `package.json` version match; gated phases untouched;
   `npm test` green at HEAD; clone synced with origin) + prints the per-repo frontier.
   `--complete`: exit 0 ⟺ all 18 runway phases done. Stamp the plan chain
   (`session-plan.py close --pr <N>`); issue #2390 stays open — it owns the build execution.
2. Fable acceptance receipt for the build orchestration sitting
   (`scripts/fable-allotment.py accept`), then **wave 1**: three lanes in parallel — DSP-P02,
   CONS-P02, NAS-P02 (9 of its 10 leaves; the real-export leaf stays gated). Sonnet builder
   agent per epic; each leaf lands module + test per the statement; leaf acceptance + `npm test`
   green before every commit; push per epic.
3. **The first completion pass runs on DSP-P02 alone** — it is the live acceptance test of D1.
   Then the pass templates to CONS-P02 and NAS-P02.
4. Subsequent waves per lane until the gated frontier: DSP→P08, CONS→P06, NAS→P07. Amendment
   micro-passes: CONS at P03 start (D3), NAS at P05 start (D4). Opus review before the five
   flagged completions (D7). `scripts/dustin-build-done.sh` runs after every completion pass.
5. Final closeout: `scripts/dustin-build-done.sh --complete` green, `no-tasks-on-me.sh`,
   `credential-wall.py --check`, `session-plan.py audit` — and the frontier report showing all
   three lanes parked exactly at their human-gated phases with levers #2367–#2371 as the only
   remaining owners.

## Premortem

- **Completion-pass deadlock** (E/H/J circularity) — mitigated by the single bundled commit and
  by running DSP-P02's pass solo first (step 3) before templating it.
- **Clones vanish again** — push per epic (D6); every write stage re-probes clone↔origin sync.
- **gh secondary rate limits** on issue-close bursts — sleep 3, ≤25 mutations/pass,
  `gh api rate_limit` between passes.
- **Capture files break check A** — every capture re-serialized through canonicalJSON before
  landing in `roadmap/receipts/` (the exact failure and fix from the 2026-08-13 session).
- **Scaffold-done illusion** (NAS-P05) and **engine overwrite** (CONS-P03) — D4 and D3.
- **Host contention** — D8 caps lanes; venture `node --test` suites are light; limen's heavy
  gates are not implicated by venture-repo work.
- **Scope creep into gated phases** — check G fails any started gated node; the done script
  asserts gated statuses byte-unchanged.

## Verification

- Per phase: `npm test`, `node bin/check-roadmap.js`, `node bin/check-roadmap.js --phase-done
  <id>`, fresh `reconcile-*.json` with `verdict: PARITY`, tag on origin — all exit codes read
  bare, never through a pipe.
- Whole build: `bash scripts/dustin-build-done.sh` (coherence + frontier) after every completion
  pass; `--complete` for the terminal claim.
- limen side: `bash scripts/verify-scoped.sh` on each PR branch; `python3
  scripts/session-plan.py audit` shows this chain with a real `PR:`.
