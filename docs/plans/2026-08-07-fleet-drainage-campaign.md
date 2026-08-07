# Fleet drainage campaign: arm the existing drain organs, wire the fleet debt registers, harvest the corpus

Issue: #1952
PR: #1956

## Context

The estate's debt, measured 2026-08-07: **1,293 open PRs** across 10 owners / 313 repos
(`docs/github-pr-debt-ledger.json`, exhaustive, cursor-reconciled), **1,417 open issues**
(`docs/github-estate-census.json`), **829 open + 356 failed_blocked + 109 needs_human**
board tasks (of 3,111), **546 local branches / 22+ registered worktrees**, and a
**742k-atom prompt corpus with 0 assessed and `Validation: FAIL`** whose source roots
point at an emptied `$HOME` while the real transcripts (12 GB `.agent-runtime`: opencode
7.8G, codex 3.2G, claude 595M; plus ~570 MB of undeclared gemini/antigravity stores)
sit unread.

Ground truth from three parallel explorations: **every layer of this campaign already
has shipped machinery.** `gitvs.py pr-debt` + the `github-pr-debt` sensor keep the PR
ledger; `github-estate-census.py` counts issues but is not beat-wired;
`owner-route-drain.py` is a shipped fleet drain (886 owner-route PRs) armed by one env;
`merge-ready.sh/.py` is the prepared mass-merge crossing whose artifact is a month
stale; `reclassify-needs-human.py` is the one sanctioned bulk board triage;
`reap-branches.py`/`reclaim-worktrees.py` carry standing grants for provably-landed
refs; `prompt-atom-ledger.py` (6,328 lines) already rebases every source root via
`SOURCE_HOME_OVERRIDE`. The estate's failure is **coverage and arming, not absence** —
the closeout predicates prove ownership topology, and nothing measures owner
throughput, so homed-but-rotting debt is structurally invisible.

## Resolved design decisions

- **D1 — Arm and widen existing organs; mint nothing.** Every front routes through a
  shipped instrument (the no-parallel-substrate rule; precedent
  `PREC-2026-08-06-external-charter-reconciles-before-adoption`: adopt by routing,
  never by execution of an outside blueprint). No new tracker, no new repo, no new
  registry.
- **D2 — The mass-merge crossing stays the operator's lever; this campaign prepares
  it.** `logs/autonomy-policy.json` names "837-PR mass merge" a separate gate and
  `docs/never-hang-permission-spec.md` keeps mass cross-org merges classifier-gated.
  The campaign refreshes `docs/MERGE-READY.md` (read-only, reuses merge-drain's exact
  classifier) so the crossing is one reviewed command (`scripts/merge-ready.sh
  --apply`), and arming `LIMEN_OWNER_ROUTE_DRAIN_APPLY=1` (sanctioned pace: 308 PRs ≈
  2–3 days, docs/plans/2026-08-06-jules-flywheel.md) is likewise recorded as his
  arming, not executed by a session.
- **D3 — The board sweep is `reclassify-needs-human.py` and the shipped repair organs,
  nothing more.** `open → archived` is an illegal canonical transition; the 356
  `failed_blocked` rows are a deliberate park nothing recycles; bulk archiving does
  not exist and will not be invented. The sweep = dry-run proposal
  (`docs/RECLASSIFY-PROPOSAL.md`) → `--apply` through the conduct broker, plus the
  beat's own `recover.py`/`heal-dispatch.py` lanes.
- **D4 — The corpus front is the reconciliation plan's successor objective 3, opened
  as its own chain when execution reaches it** (per the 2026-08-06 ruling: "its own
  plan+issue+PR"). Scope there: `SOURCE_HOME_OVERRIDE` rebase onto
  `.agent-runtime`/real stores, cursor refresh, one bounded disposition batch per
  `docs/prompt-corpus-policy.json`; the gemini/antigravity vacuum (~570 MB on disk,
  declared `unpopulated`) becomes declared corpora rows + a widened source glob.
  Homing is distillation, never transfer: atom statements never enter the public
  tree (`check-atom-homing.py` check D); `redacted: false` stores never leave their
  homes; FERPA-flagged `composition-1-2` stays excluded. Nothing in `.agent-runtime`
  or the atom ledger is deleted before ingestion.
- **D5 — The register work is the two real gaps, not a rebuild:** beat-wire
  `github-estate-census.py` (a `sensors.yaml` entry + `parameters.yaml` params, per
  check-sensors A–F; heartbeat source + cadence = auto-reachable) and note the
  mergeable-state gap (`gitvs.py`'s PR query omits
  `mergeable`/`mergeStateStatus`/`reviewDecision`) as the ledger's next field. The
  drifted snapshots (310 vs 313 repos) reconcile by refreshing both from the same
  run.

## Steps

1. **Plan chain** — issue #1952 + this plan + implementing PR (this file's `PR:` line
   stamped by `session-plan.py close`). ✅ opened 2026-08-07.
2. **MERGE-READY refresh** — run `python3 scripts/merge-ready.py` (read-only); ship
   the regenerated `docs/MERGE-READY.md` via `scripts/ship-docs.sh`. The operator's
   crossing is then: review the READY set → `scripts/merge-ready.sh --apply [--limit N]`.
3. **Board sweep** — `python3 scripts/reclassify-needs-human.py` (dry-run →
   `docs/RECLASSIFY-PROPOSAL.md`, shipped), then `--apply` (broker-mediated; FLIP
   rows reopen, CHRONIC rows park with evidence, KEEP/STALE/REVIEW reported).
4. **Register wiring** — one `feat/` PR: `sensors.yaml` entry `github-estate-census`
   (heartbeat, gate + cadence + timeout params declared in `parameters.yaml`,
   `severity: advisory`), modeled on the `github-pr-debt` entry's due-check pattern;
   refresh `docs/github-estate-census.json` in the same run to clear the 310-vs-313
   drift. `check-sensors.py` + `check-params.py` green before push.
5. **Branch/worktree reap** — `python3 scripts/reap-branches.py --apply` (standing
   grant: landed-ancestor + merged-PR classes only; LIVE-WORK never deleted) and
   `python3 scripts/reclaim-worktrees.py` (clean+merged+idle standing-grant classes);
   receipts to the acceptance ledgers; regenerated `docs/branch-hygiene.md` ships.
6. **Corpus drain pilot** — open its own chain (D4) and execute the bounded batch;
   file the gemini/copilot corpora declarations there. Owner:
   `scripts/prompt-atom-ledger.py` organ + `corpora.yaml`.
7. **Throughput visibility** — with the estate census beat-wired (step 4), the
   pr-debt trend (`pr-debt-trend.py --check`) plus issue/branch counts give the
   fleet-debt series; a queue-age-per-owner threshold param lands with step 4's
   sensor if cheap, else is filed on the sensor's owner.

## Premortem

- **What most plausibly makes this wrong or unwelcome?** (a) Merging or closing at
  fleet scale without the operator's crossing — held off by D2: sessions only
  classify and prepare; arming commands are recorded, not run. (b) A board sweep
  that fights TABVLARIVS — held off by D3: only the sanctioned triage organ, only
  broker writes. (c) The corpus front leaking transcript text into a public tree —
  held off by D4's homing-is-distillation constraints and `check-atom-homing.py`
  check D. (d) The 16 GB host jetsam-killed by parallel heavy runs — steps run
  serialized; `verify-whole.sh` is machine-serialized already. (e) `merge-policy.sh`
  applied to foreign repos misclassifies deploy-sensitivity (it derives from limen's
  GATES registry) — foreign-repo merges stay with each repo's own charter/owners;
  this campaign does not merge outside limen.

## Verification

- `bash scripts/verify-scoped.sh`
- `python3 scripts/check-session-phase.py` (chain green)
- Step 4: `python3 scripts/check-sensors.py && python3 scripts/check-params.py`
- Step 5: `python3 scripts/reap-branches.py` dry-run re-run reports zero remaining
  provably-landed branches (idempotent fixed point)
- Campaign fixed point: `scripts/no-tasks-on-me.sh` exit 0 AND every armed/deferred
  action cited to its registry owner (lever, sensor, or acceptance ledger).
