# FULL → HEAL → EXPAND → EVOLVE — estate plan

Issue: #1922
PR: (pending)

## Context

The 2026-08-06 notification storm (60+ "PR run failed" notifications) root-caused to a single
mypy error on main (`owner_route_drain.py:65`, from the merge-rail change) mirrored into every
PR gate. Healing it exposed the real problem set: the session orientation was reporting omega
state from a **two-week-stale stamp** (`logs/omega.json`, 2026-07-22, a 30-rung contract; the
live contract is 13 core + 24 sensor rungs), a registry-declared rung `omega.sh` never ran
(`core.autonomy-acting`, added by #1827 registry-side only — CONTRACT INVALID, main's verify
job red), worktree debt at 15, the jules flywheel 7/8 landed, and two recurrence guards that
are genuinely unbuilt (a cross-source notification-storm sensor; a review-comment drain
organ). This plan is the full arc: heal every red to the fixed point, expand the drained work
surface, evolve the structures so the storm class cannot recur.

## Resolved design decisions

- **D1 — Re-measure before healing.** The "19 PASS / 10 FAIL" headline was a stale-stamp
  ghost; the fresh offline measure found 3 det FAILs, of which one was a worktree artifact.
  Healing proceeds only from fresh predicate output, never from the orientation line.
- **D2 — Fix the enactor, not the registry.** For `core.autonomy-acting` the registry row was
  correct and the call site was missing; the repair added the rung to `omega.sh` at its
  registry position (shipped: #1921). The identity check that failed closed stays untouched.
- **D3 — Storm prevention is a sensor, not a mute.** Per the session-noise-containment
  doctrine (distillation, never disable-to-silence), the evolve item is a first-class
  cross-source rate predicate, not any notification cap.

## Steps

1. **HEAL / done this session** — mypy red: #1916 merged (another lane's format fix
   verified, landed by the merge rung). Omega contract: #1921 merged (`autonomy-acting`
   call site + test stub; omega.test.sh 17 checks PASS). Experience registry parity:
   restored the evacuated `organvm-corpvs-testamentvm` clone to `~/Workspace` — doctor
   green. Handoff rung: verified green against the live root (worktree artifact only).
2. **HEAL / open, owned** — `core.ask-lineage`: journals reference private raw objects
   absent from the sharded store (`.limen-private/session-corpus/prompt-atoms/raw-objects`,
   869MB survives; a subset lost in the 2026-07-27 evacuation); `--rebind-checkpoint`
   refuses, correctly. Owner: `tabularius` per `omega-remediations.json`; needs a bounded
   object-recovery pass against the T7 evacuation store before any rebind.
3. **HEAL** — worktree debt 15→0: the one pre-accepted candidate (`.worktrees/charles`,
   clean+pushed+idle) belongs to the beat's reclaim rung (interactive apply is
   classifier-blocked in bg sessions); the 10 dirty / 1 unpushed trees each get a per-tree
   disposition (commit+push or acceptance line in `docs/worktree-reclaim-acceptance.jsonl`).
4. **HEAL** — externals: `organvm-i-theoria/.github` Health Check / SLA / Metadata
   Reconciliation (all red at f430004, hourly) and `organvm-vii-kerygma/stakeholder-portal`
   Maintenance Cron → HEAL-cifix owner-routed tasks via `scripts/self-heal.py`'s class.
5. **EXPAND** — land #1893 (`feat/jules-flywheel`, PR-H, DIRTY): rebase onto healed main,
   CodeQL reruns, merge via `merge-policy.sh`; then `session-plan.py close
   2026-08-06-jules-flywheel --pr 1893`; the residual human atom (`launchctl kickstart -k
   gui/$UID/com.limen.heartbeat`) files as a lever in `his-hand-levers.json`.
6. **EXPAND** — review debt: resolve CodeRabbit actionables (#1894: 12, #1893: 4, #1899: 2)
   through the `preflight-thread-state.py` ack rail; PR-estate hygiene: close one of the
   #1795/#1796 duplicates; `GITVS-UNCAPPED-PR-DEBT-0715` stays untouched under
   `operator-paused` — on release its discharge is its own predicate
   (`gitvs.py pr-debt --check`; the drain organ shipped in #1881).
7. **EVOLVE** — notification-storm sensor: one `sensors.yaml` entry + script computing a
   cross-source rate (CI failures + HEAL-cifix rows + notifications per window), constraint
   per D3. Stamp-freshness guard: orientation flags/refuses an omega stamp older than a
   beat-cadence bound. Declare the three gated-organ master gates
   (`LIMEN_NOMENCLATOR`, `LIMEN_POSITIONING`, `LIMEN_AVTOPOIESIS`) in `parameters.yaml`.
   DISCOVER-task terminal states must write `value-discovery-dispositions.json`
   (0 recorded vs 156 terminal today) with a parity check. Review-comment drain organ under
   GITVS (`institutio/registry/organs.yaml:141` already names it).

## Premortem

- **What most plausibly makes this wrong or unwelcome?** Treating the estate program as one
  session's checklist: steps 2–7 are owned, multi-session work; forcing them into one lane
  would recreate the heterogeneous-branch defect the chunking rule exists to prevent. The
  plan is wrong if any step ships without its own one-concern branch and predicate — or if
  the ask-lineage recovery is attempted as an improvised copy instead of a bounded,
  receipt-backed pass by its owner.

## Verification

- `bash scripts/verify-scoped.sh` per branch; `scripts/merge-policy.sh <PR#>` per merge.
- Fixed point: fresh `scripts/omega.sh` run exits 0 (or every FAIL carries typed owner-routed
  remediation); `scripts/worktree-debt.py --strict --fail-on-debt` exits 0.
- Closeout pair green: `scripts/no-tasks-on-me.sh` and `scripts/credential-wall.py --check`.
- Each EVOLVE item lands with its own registry parity check red-on-drift in pr-gate.
