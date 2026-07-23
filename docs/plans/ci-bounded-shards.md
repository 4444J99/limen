# CI bounded-shard owner plan

Owner: Limen gate registry and CI workflow.

## Observed defect

Exact-head run `29340908636` began at `14:27:18Z` and finished its final verify job at
`14:57:36Z`. The critical path was about 30 minutes because `python` first ran the API/CLI suite,
then `verify-whole.sh` serially repeated that suite, runtime probes, and the web build after their
dedicated jobs had already passed. This is duplicate execution, not a justified integration seam.

## Target form

- Derive named shards from the gate registry and each gate's execution profile.
- Give every shard one owner, predicate, input hash, timeout, finite transient-retry policy, output
  cap, and content-addressed receipt.
- Run independent shards in parallel remotely; let the local orchestrator derive safe concurrency
  from host pressure.
- Make the final job validate shard coverage, hashes, and genuine cross-module seams only. It must
  not rerun a successful child.
- Keep `verify-whole.sh` as a thin compatibility entrypoint over the same shard registry.

## Predicate

1. Every registered gate resolves to exactly one shard and execution profile.
2. A fixture failure identifies one shard without erasing successful shard receipts.
3. Static validation rejects duplicated child commands in the aggregate job.
4. Timeouts, retries, and output bounds come from declared parameters, not workflow literals.
5. Online and offline aggregate passes preserve current coverage and produce byte-identical receipts
   on an unchanged second pass.
6. The receipt reports measured critical-path change; no arbitrary duration target manufactures green.

Receipt target: a focused Limen PR that supersedes this plan and links exact-head CI evidence.

## Decision record — fleet ownership & the jurisdiction principle (2026-07-22)

Asked: *"who needs to own CI work at large so this is universal context? do we need a repo?"*
Recorded here so it is never re-derived (the agent-all precedent: converge, don't rebuild).

**No new repo.** CI-at-large decomposes onto three owners that already exist:

| Concern | Owner (exists today) |
|---|---|
| Doctrine + audit | limen — `AGENTS.md` → Bounded Composition + Session Discipline (check M in `scripts/check-agent-docs.py`), the GATES registry pattern, `institutio/github/estate.yaml` `classes[].required_checks`, the GITVS doctor |
| Distribution | the per-org `dot-github--*` repos (7 live, template-flagged; theoria's description is literally "Organization-wide CI/CD") — reusable `workflow_call` workflows; member repos become thin shims; GITVS holds parity |
| Labor + state | the TABVLARIVS board — the existing `heal-cifix-*` lane already dispatches per-repo CI repair |

A separate CI repo would split authority from `estate.yaml` (which already declares
per-class required checks) and violate the settled converge-not-rebuild rule
(`docs/agent-instruction-standard.md`).

**The meta-defect the 2026-07-22 de-dup series kept finding — unscoped authority.**
Every instance of the sprawl was a gate applied outside its jurisdiction:

- `verify.py`'s deploy escalation constrained the PR lane (a push/deploy concern) — #1382;
- `tasks.yaml` (a data concern) classified as a website deploy — #1385;
- ci.yml's `verify` aggregate re-proved its children's lanes — #1384;
- merge-policy's pending-count lets advisory checks veto the merge lane — open;
- local host-admission (a host-execution concern) was consulted to withhold CLOUD dispatch
  to Jules (2026-07-22 Codex session) — the same defect one lane over.

Principle (sibling of "a sensor without an effector is a defect"): **a gate without a
declared jurisdiction is a defect** — it defaults to constraining everything it can reach,
and fail-toward-caution without a scope boundary metastasizes into fail-toward-everything.
Target form: gates / sensors / admission surfaces carry a declared `jurisdiction`
capability (`local-exec` | `pr-lane` | `merge` | `deploy` | `cloud-dispatch`); consumers
honor a gate only inside its jurisdiction (read by capability, like sensors.yaml's
`omega_eligible`); a predicate reds any consumer honoring a foreign gate. Host admission's
jurisdiction is local execution only — remote rails (Jules, Copilot cloud, dispatched
workflows) must never consult it.

**Build list (tranche 2, after the in-flight series #1382/#1384/#1385/#1386):**

1. `jurisdiction` field on GATES/SENSORS/admission surfaces + the consumer predicate.
2. Reusable scoped-verify workflows in `dot-github--*`; member-repo workflows become shims.
3. A GITVS doctor class auditing member-repo CI for duplicate suites, unscoped runs, and
   missing caches → board tasks into the heal-cifix lane.
4. `estate.yaml` `classes[].ci_posture` declaring the desired CI form per repo class.

## Measured outcomes — the de-dup series landed (2026-07-23)

All series PRs merged: #1382 (kill the PR-lane whole-matrix escalation), #1384 (one owner
per proof in ci.yml), #1385 (board fast lane), #1390 (pytest-xdist + moneta npm cache),
#1391 (path-aware main-green + tasks.yaml off ci.yml push paths), with records #1386/#1388
and side-fixes #1403 (cells `ps -ww`), #1424 (main-green queue proof), #1432
(no-tasks-on-me SIGPIPE). Before → after, measured on live runs:

| Lane | Before | After |
|---|---|---|
| Board-class PR | 39.5 min, suite ×4 (#1372) | non-deploy under merge-policy (#1334 print); queue validation 27–61 s |
| Workflow-class merge groups | serial suite each | 27–61 s (#1384 32s, #1403 32s, #1409 27s, #1420 39s, #1421 61s) |
| cli-touching pr-gate | ~17–20 min serial | 10m02s green under `-n auto` (3,772 tests); merge-group 7m12s |
| Last serial group | — | #1391 at 19m53s — the final serial validation |
| main push post-merge | full CI re-run | Fleet Gate ~1 min; head already proven exact in its merge group |
| main-green sensor | red on cancelled/docs heads | GREEN queue-proven both modes (#1424) |
| Actions minutes | ~494 min/day (day-18 snapshot: limen 42,414 org-min) | next usage snapshot owns the number; expected band 150–220 |

xdist canary: two consecutive green Linux suite runs; one load-shaped budget fix
(host-admission shell-helper subprocess timeout 10s→60s — interpreter-spawn latency on a
saturated runner, not an ordering flake; `xdist_group` would not have helped).

**Meta-defect ledger update (2026-07-23):**

- merge-policy pending-count lets advisory checks veto the merge lane — **still open**. New
  specimen: its BLOCKED prose reads "a required check never ran" while its own counter
  prints `failing=1` — a failed check misdiagnosed as a missing one (#1390 at 10:18Z).
- **Closed by #1424:** check-main-green anchored on the newest ci.yml push run even when it
  was a superseded cancellation — under a busy queue 3 of 4 push runs cancel within
  seconds, so the sensor sat red on a proven trunk. The queue rail is the proof rail: a
  `pr-gate merge_group success` at the exact head now proves it in both modes. Same
  jurisdiction shape — a push-lane proof-form was demanded where the queue lane owns the
  proof.
- **Closed by #1432:** the closeout predicate's stranded-ref check false-failed via
  SIGPIPE+pipefail once `his-hand-levers.json` outgrew the 64KB pipe buffer.
- Recorded follow-on (D-1): build the attach-grace into `await-pr.sh` — arming before check
  suites attach reads as false-BLOCKED; the bounded attach-guard was hand-run 4× on
  2026-07-23 — plus printed-verdict/exit coherence.
