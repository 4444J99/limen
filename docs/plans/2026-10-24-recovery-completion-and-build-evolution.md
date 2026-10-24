# Recovery completion and build evolution plan

Issue: #3173
PR: (pending)

Status note: planning deliverable; implementation, installation, deployment, native archival and reclamation have not been performed by this plan.
Date: 2026-10-24 UTC.
Coordinator: current direct Codex planning session; the original 25 screenshot identities remain fixed in the existing census.
Spec: the operator's October 24 report and instruction to fill all gaps, finish remaining moves, and critique/evolve the build, subject to each original owner's acceptance.
Canonical owner: https://github.com/4444J99/limen/issues/3173.
Supersedes the execution order in docs/plans/2026-10-23-suggested-session-closeout.md; preserves its evidence and every original acceptance condition.

## Context

The prior work landed seven PRs, reconciled all 25 screenshot sessions and safely removed six local branches. It did not prove full task completion or canonical release. The supplied 08:43 EDT report records 21 archived sessions, 22 retained rollout files, two missing execution roots, an unrecovered original HTML, unapplied phase-skill changes, and unresolved deployment/native/device acceptance.

Planning-time refresh:
- GitHub main was 2a45e7b65846c7a5ec5182435057603a152595ea at 12:50 UTC, after #3201 landed during inspection; it advanced again to 21e945016ab259db42aac92d1aad5e3e5fa477b3 by 12:59 UTC. The plan publication branch is based on the latter. The supplied 3de53f4a target is historical; no implementation target is frozen by these observations.
- The live checkout remains clean at 0a6622ca. Its cached tracking ref is not fresh remote proof. Installed 0e35ac43 is the supplied report's observation, to be refreshed before adoption.
- Host status reports no active lease, but its pressure sample is 2026-10-23T13:42:04Z. A no-probe status response is not fresh heavy-work admission.
- Internal available space measured 98,805,760 KiB, about 94.2 GiB. The ordinary reopening latch remains 200 GiB. External capacity cannot clear the internal latch.
- The local policy is observe mode, dispatch disabled, approved_priorities empty. Planning does not enable autonomy or replenish the original allowance.
- Read-only native reconciliation confirms 25 identities, 21 archived and four unarchived; 22 rollout files exist. The additional AV archive was at 2026-10-24T05:46:58Z. Archive actors beyond the coordinator's four actions remain unattributed.
- #3145 and #3175 are closed. #3003, #2054, #3118, #2977 and the original project owners remain open.
- Existing receipt producer PR #2988 is open and ready for review, head a58b04a80b415671f3020b685a364628706cc112 at inspection. Its existence and historical tests do not prove current release readiness.
- Domus #554 is an issue containing a tested launcher/interrupt patch, not a landed PR.

These observations have separate timestamps and sources. Refresh only the facts needed at a transition; do not rewrite the historical receipts or keep rebasing a verified change whenever main moves.

## Goal

Prove every original task's acceptance and every session's release from exact, published evidence, with complete custody and safe checkout dispositions; improve the existing build so future sessions produce the evidence release needs.

Two independent targets apply:
1. Session reconciliation/release: 25/25 original identities have valid terminal session evidence and native archive readback where eligible.
2. Original work completion: every owning project predicate passes, including research, service, restoration and physical/artistic acceptance.

A valid handoff can release ephemeral session responsibility while an original task remains open. It cannot satisfy target 2. Neither target is achieved by an archive count, merge count, admitted checkout, published plan or accepted loss report.

## Approach and design

Extend the existing census, broker, gate registry, custody graph, receipt producer, process contracts, reclaimer and Domus source ownership. Do not create a replacement task registry, second configuration writer or new control plane.

Recovery first is the selected engineering approach. Parallel implementation of every row would collide with storage, budget and writer limits. Another audit-only checkpoint would leave the same acceptance gaps. Use one recovery writer, then bounded owner packets ordered by dependency and preservation risk. Independent project acceptance need not wait for an unrelated missing artifact.

```text
T0: scope, authority and allowance -> T1: admitted source lane -> T2: build repairs
 |                                                             |
 +-> T3: bounded original custody recovery                      |
            |                                                  |
            +---- required inputs for each owner only ----------+
                                      |
                          T4: that owner's adoption
                                      |
                          T5: that owner's acceptance
                                      |
                    T6: exact-session release, when eligible
                    (complete or evidence-backed valid handoff)
                                      |
                         T7: archive and safe disposition
                                      |
All original T5 predicates + all required T6/T7 proofs -> full aggregate completion
```

The arrows describe each owner's dependencies, not global barriers. T3 may proceed as bounded read-only recovery alongside admitted work. T4 waits only for its required recovered inputs; eligible T6 releases may proceed before unrelated T3/T5 completion, including a valid handoff with full release/custody evidence. Full aggregate completion still requires every original task predicate. No second recovery writer or additional heavy job is implied.

## Constraints and binding surfaces

- Planning scope ends at defining and publishing this plan. No autonomous goal, scheduled run, deployment or implementation starts from publication.
- Implementation authority and cumulative usage come from the existing owner and keeper executionAllowance. Unknown/exhausted allowance holds dependent execution. Splitting, restarting or renaming does not reset it.
- Preserve one recovery writer, at most two implementation tasks estate-wide, one heavy workload, 30-minute attempts including at most 10 minutes verification, and 120 cumulative agent-minutes per approved outcome including descendants. One corrective retry requires changed inputs.
- Check ownership, branch, worktrees, broker claims and host admission before source mutation. Reuse a positively inactive admitted checkout; never adopt one merely because it is clean.
- Preserve every agent lane, native chat, database/WAL, private/ignored payload, dirty worktree, protected session and unavailable-volume record.
- Scope new-worktree admission to the measured physical capacity pool. Do not lower or clear the 50/200 GiB latch. Use an already authorized repair route only with its exact reservation, byte ceiling, retained-checkout owner and deadline.
- Stage bulk custody under the configured custody-staging root outside vendor runtime state, with mode 0700, capacity accounting, hard deadlines and retained partials.
- Changes to managed configuration land in source and use scoped chezmoi render/apply. Preserve app/operator-owned model, effort, trust, UI and hook decisions.
- Use the registry's implicated checks, exact-head PR rail and one merge submission. No synchronous CI polling, full-suite replay without changed inputs, direct trunk push, force-push, test disabling or capability removal.
- Human-only credential, spending, protection, rights and artistic decisions remain in their existing lever/credential/project owners. Do not create an approval gate for routine engineering.

Binding references: AGENTS.md; docs/architecture/finite-workspace-recovery.md; docs/architecture/concurrent-integration.md; docs/session-closeout.md; institutio/governance/gates.yaml; existing broker and credential ownership records.

## Build critique and disposition

| Finding | Disposition and proposed improvement | Acceptance |
|---|---|---|
| Source merges outrun installed/runtime acceptance; main moves during reporting. | Accept. Record a target vector per tranche: repository/head, installed CLI, Worker version, protocol digest and source/config generation. Extend existing receipts rather than one ambiguous status. | A merge cannot set deployed/observed/released; runtime readback binds the intended compatible implementation. New unrelated main commits do not trigger endless revalidation. |
| sync-release invokes bare python3 for contention and proceeds when the probe is unavailable. | Accept. Resolve the interpreter through the existing resolver; distinguish free, occupied and unmeasured. Hold destructive switch/reset/stash on unmeasured occupancy. Preserve the existing clean fast-forward policy, with current cleanliness and target checks; any broader change to that policy needs its own explicit reviewed rationale. | Missing dependency, malformed output, timeout or unreadable census cannot reach a destructive valve. Occupied paths remain protected. Clean no-op/fast-forward behavior has explicit regression coverage. |
| Legacy custody attestations and validated restoration graphs have different assurance. | Accept with compatibility. For new recovery releases, require a typed custody result and validate the graph; support evidence-backed absence of local-only payload for repository-only scopes. Keep legacy receipts readable as historical evidence. Retirement already requires stronger portable custody and must retain it. | verified:true plus an arbitrary hash-bound JSON file cannot prove new recovery release. Wrong session/scope, missing replica/readback or incomplete restoration blocks. No retroactive claim that every legacy receipt is false. |
| Native process attribution has stronger Codex support than other lanes. | Accept. Extend existing conduct/native launch witness adapters and Domus process contracts, retaining PID/start identity, session/root lineage and executable/config/lifetime bindings. | Positively classify supported lanes and shared services; PID reuse, ambiguous helpers and unknowns still block. Never solve unknown ownership with basename or daemon-subtree exemptions. |
| Reclaimer summaries do not always supply the historical retirement graph consumed by closeout. | Accept prospectively. Have the existing reclaimer publish write-ahead session/scope/custody/dependency evidence and an atomic completion observation consumable by scope_retirement.py. | Interrupted transitions preserve recoverable data. External Git consumers prevent retirement. Every newly retired session-owned root in the declared action class has the required packet; a second pass is unchanged. This cannot manufacture missing historical evidence. |
| The census is multiple snapshots, and prompt documentation still contradicts landed repair evidence. | Accept. Add a derived validator/renderer over the existing receipt directory, with immutable observation generations and per-dimension evidence. Reconcile stale owner READMEs through exact source evidence. | Exactly 25 original IDs; coordinators/descendants separate; no mixed-generation counts or archive-to-release inference. Unknown actor remains unknown unless evidence establishes it. |

## Work packages

Each package ends with a pushed artifact/receipt in its existing owner and a retained-checkout or custody-qualified retirement disposition. Independent review covers the exact final change; reuse unchanged valid verification fingerprints. Do not treat these packages as new allowances.

### T0 - Freeze scope, authority and the executable gap map

Owner: Limen #3173. Inputs: original census, current native API/database, original task prompts/receipts, existing owner issues, live refs and keeper graph.

- [ ] Refresh the fixed 25 identities against native API and read-only database; retain native archive timestamps and unknown actors. Track this planning coordinator and any descendants separately.
- [ ] Resolve actual repositories, original roots, subject heads, owner predicates and existing handoffs. Separate missing roots from unavailable mounts and prunable metadata.
- [ ] Read keeper executionAllowance, remaining cumulative usage, approved priorities, deadline and lease/path claims. Preserve unknown legacy debits as unknown; no provisional budget admission.
- [ ] Capture one timestamped target vector and relevant host/quota/storage observations. Derive the admitted ready set from dependencies, not from easy-to-merge work.
- [ ] Define the derived projection over the existing census without implementing it before admission. T2 owns scripts/check-session-closeout-census.py, cli/tests/test_session_closeout_census.py and its gate in institutio/governance/gates.yaml. Proposed projection fields per session: identity, observation_generation, original_owner, scope_ids, source_publication, installed, runtime_observed, task_acceptance, custody, process_coverage, release_checks, archive_state, checkout_disposition, evidence_refs. Each dimension carries measured state and evidence/time; unavailable evidence never maps to pass.

Output: a published 25-row gap map and bounded next packet with real authority/allowance, or an exact held prerequisite under its existing owner.

Tests for the new consumer: duplicate/missing/extra screenshot ID; separate coordinator; conflicting generation; stale observation; unknown archive actor; merged-but-not-deployed; archived-but-unreleased; exit 2; handoff-with-unfinished-task. All must preserve the relevant gap.

### T1 - Establish an admitted execution path

Owners: #3173 and existing inventory/host/runtime owners; Domus #554 for its patch's location hold.

- [ ] Prefer an existing positively inactive checkout after writer, broker, dirty/private payload and process checks.
- [ ] Otherwise use the normal workstream on a verified mounted, accessible independent capacity pool with lane-correct credentials and current admission.
- [ ] If ordinary admission is held, evaluate only the existing bounded repair-checkout contract: accepted storage_repair priority/reservation, one checkout, 256 MiB ceiling, safety floor, retained ownership and original allowance. Do not use closeout-only read-only isolation for implementation.
- [ ] For Domus #554, resolve its specifically pending location/TCC predicate without assuming a generic policy exception covers that checkout. Preserve the retained patch and existing branch.
- [ ] Resolve the complete gate toolchain before allocating or running checks. A missing interpreter/package and a broker/credential denial are different failure classes.

Output: one exact owner checkout/branch, lease/reservation, byte/deadline measurement and runnable scoped toolchain. If unavailable, retain the dependent packages; continue independent read-only recovery. No unchanged denial retry or replacement reservation.

### T2 - Repair the evidence-producing build

Owners: #3173 sync/census; #2977 and existing PR #2988 receipt production; existing process/custody owners.

- [ ] Implement T0's derived census validator/renderer and its negative controls after T1 admission, without a second task registry.
- [ ] Implement the selective contention correction in scripts/sync-release.sh and its existing helper/test surfaces. Cover bare-interpreter failure, unmeasured/occupied/free output and all destructive valves using cli/tests/test_sync_release_census.py, cli/tests/test_session_contention.py and scripts/tests/sync-release.test.sh.
- [ ] Review #2988's exact diff, outstanding findings and current scoped evidence. Complete/adapt that producer rather than create a competing one. Its plan/build/check stages must derive from original identities and original owners; dry-run/unpublished output is not publication or release evidence.
- [ ] Strengthen new recovery receipt custody validation in cli/src/limen/session_closeout.py with cli/src/limen/portable_custody.py. Cover arbitrary attestation, wrong scope/session, missing restoration/readback, explicit no-private-payload proof and legacy compatibility in existing closeout/portable-custody tests.
- [ ] Add missing native witness adapters in cli/src/limen/process_ownership.py and process_services.py, with Domus's executable_domus-process-ownership source. Test native lane identity, PID reuse, detached helpers, stale config and protected/shared services.
- [ ] Bridge future reclamation evidence in scripts/reclaim-worktrees.py and cli/src/limen/scope_retirement.py only for retirement of a native-session-owned declared scope used by canonical closeout. Derive identity from that session's broker/continuation/subject binding, never the newest transcript or Git author. Retain a candidate lacking that provenance when session retirement is required. Generated/tool-cache residue keeps its existing separate allowlisted lifecycle; legacy reclaimer records remain historical evidence and cannot be upgraded from publication to restoration proof. Test interruption before/after each durable transition, active/external consumers, ignored payload, changed remote head, absent mount, unregistered candidates and idempotent recovery.

Output: small independently reviewable changes with negative controls, exact-head verification, publication and adoption receipts. These improvements prevent new gaps; they do not establish past custody.

### T3 - Recover originals and prove independent restoration

Owners: #3173; prompt research #3056; Domus #535; existing private archive/custody owners.

- [ ] Inventory the two missing execution roots without recreating them. Search only positively relevant reclaimer/move receipts, existing backups, retained native writes and custody locations. Preserve negative results and mounted-volume identity.
- [ ] Preserve and reverify the exact recovered original snapshot, corrected snapshot/HTML, candidate HTML and reconstructed phase-skill packet as separate objects. Retain their existing private hashes and lineage.
- [ ] Resume original HTML recovery only on a new bound copy or original render-input/write evidence. Do not rerun the two failed renderer hypotheses unchanged. Visual resemblance and DOM validity cannot prove original bytes.
- [ ] Account for all three missing rollout bodies individually: recover an authentic retained copy/native export with identity proof, or keep body recovery unproven. Native database/archive records alone do not recreate content.
- [ ] Restore the 13 reconstructed phase-skill artifacts from their published private exact commit into independent staging. Verify manifests, content, metadata actually preserved, validators and source patch. The missing historical quick_validate.py and original filesystem metadata remain separate recovery obligations.
- [ ] Use the existing native capture/portable custody path to capture Git objects plus dirty, ignored, untracked and native state where required. Perform the required independent full restorations and readbacks; native SQLite capture includes appropriate consistency/WAL handling.
- [ ] Bind every original scope to complete custody/dependency evidence. An already missing root is not a valid retired root without truthful contemporaneous evidence satisfying the retirement contract.

Output: authenticated independent readback, restore comparison and complete session/scope custody graph. If an original is irrecoverable, publish a precise loss/evidence-gap disposition under its existing owner and seek only the genuinely required owner ruling. This is honest resolution of a recovery attempt, not fulfillment of the missing original or permission to claim full completion.

### T4 - Adopt source, configuration and the live broker

Owners: Limen #2848/#2054/#3118; Domus #535/#554/#547.

- [ ] Capture a fresh exact compatible target vector. Use only scripts/sync-release.sh for live adoption and the Domus install rail for CLI/protocol adoption; record current source and installed digests separately.
- [ ] Apply recovered phase-skill fixes to their actual Domus source files after original/draft hash comparison. Preview a scoped chezmoi render, run applicable skill/frontmatter validators, apply only named targets, read back installed hashes and verify a second render/application changes nothing.
- [ ] Complete #535's config review independently: native schema/doctor recognition, ownership-limited modifier diff and preserved app state. A justified no-op is valid for config cleanup; it does not apply the phase-skill repair or fix a vendor tool-contract defect.
- [ ] Land #554's existing diagnostic and terminal-interrupt correction under its exact source branch/admission. Repeat the implicated wrapper/terminal tests against current code; then apply only the two owning targets and verify one terminal SIGINT, continued native lifetime/reservation and release on actual exit.
- [ ] Read and explicitly dispose every #3118 finding. Include the real deployed storage/migration/rollback smoke and operation write-count/CPU measurements; do not rely solely on the 413 historical Worker tests.
- [ ] Identify the deployed Cloudflare Worker version before claiming #3117 adoption. Use the manual exact-head deploy-worker.yml rail only with existing deployment authority. Bind expected main SHA, workflow/version readback, persistence mode and rollback version; do not redeploy if the desired version is already proven.
- [ ] Prove broker recovery with #2054's actual non-Codex Agy canary: capabilities, native registration, bounded read/no-op claim, schema-valid report/harvest; rerun PSP-P00-W07 #2165 against that receipt. Preserve identity, no generic-token substitution, no spending/account change to mask a code defect.
- [ ] Verify #547's retained package lifecycle and fresh OpenCode behavior. Potential credential exposure is assessed and any necessary rotation stays in the credential owner's authorized procedure with redacted evidence.

Output: distinct merged, installed, deployed and runtime-observed results, with config idempotence and bounded broker persistence/native acceptance. Passing runtime-lag alone is insufficient.

### T5 - Finish the original owner predicates

The following 17 grouped rows preserve all 25 original sessions. Each row must expand from the canonical census's exact IDs, roots and original prompt before implementation. Counts are denominators, not success claims.

| Session group | Count | Existing owner | Required next move and acceptance |
|---|---:|---|---|
| Audiovisual next steps | 2 | Audiovisual #12 | Publish the existing complete 15-project first-packet plan from its retained runtime-only artifact into its canonical project owner. Resolve original allowance/admission without a fresh identity; execute approved first packets and record artistic/device acceptance for each required output. |
| Private audiovisual archive | 1 | Existing private estate-vault #6 | Reconcile newer history, remaining native bodies/deferred Codex source, 67 historical gaps and SSD/Photos coverage; preserve source media; finish authenticated independent readback and native restoration. Draft PR publication alone is insufficient. |
| Prompt-sequence studies | 3 | #3056; draft #3067; landed #3189 | Reconcile obsolete #3087/not-yet-repaired README claims, preserve the 382-column/3,500-row population and the 29-association/28-position repair evidence, finish remaining source/annotation/research review and permitted browser visual acceptance. Do not bypass the prior browser security prohibition. |
| Runtime audit and repair | 2 | #2848; landed #3124/#3130 | Complete all six agent lanes' source/runtime mapping, rollout, native diagnostics and custody. Preserve capabilities/auth-needed rows. Verify the original audit/repair session bindings instead of substituting this coordinator. |
| Codex configuration and phase skills | 2 | Domus #535 | Complete T3/T4 content restoration, three source repairs, scoped application, config cleanup or justified no-op, and fresh native skill/config acceptance. |
| Broker quota recovery | 1 | #2054/#3118; landed #3117 | Finish exact Worker adoption, migration/rollback evidence, non-Codex canary and #2165 acceptance; disposition every review finding. |
| Scope/stale-binding repair | 1 | #3001; draft #3042 | Resolve original accepted findings: expired lease/run reconciliation, protected operator release, nonmutating replacement validation and tombstoned reservation retention. Verify safety before activation; a green source diff is narrower. |
| Six-vendor Insights | 1 | #2887/#3084 | Preserve the dirty implementation/test/plan, produce fresh source-fingerprinted reporting and finish all six vendors' decoder/coverage checks. Decode opaque Antigravity sources or return explicit unreadable status/nonzero exit; keep vendor-template defects with their vendor owner. |
| OpenCode access reconciliation | 2 | #2961 | Complete native authenticated gateway execution, lane-correct registration/reservation/report/harvest and gateway acceptance. A gateway capability list is not native execution. |
| TMB playback | 1 | TMB #14/#16; draft #18 | Correct observer/exit semantics; measure natural playback with independent clocks and the original 0.95 Safari full-tier threshold, plus physical audio/video acceptance. Preserve the required 1,800-second soak; it needs specific bounded authority exceeding the normal ten-minute verification allowance. Retain draft state until the original predicate is met. |
| VS Code setup | 1 | #3173 and census-linked setup evidence | Reopen the original request/receipt, verify canonical workspace paths and native workspace loading, then source/config/custody/release checks. Historical setup prose is not current native acceptance. |
| Live-coding plan review | 1 | Existing response-only owner | Preserve the completed review and native transcript. Verify read-only/response-only release; no unrelated implementation added. |
| Empty usage-limit probes | 3 | Existing probe owners | Prove failure before tool execution and absence of created effects; preserve archived native transcripts and read-only release evidence. |
| PSP-P00-W02 executor | 1 | #2160 / landed #2292; #3173 recovery | Preserve the accepted validator and passing task predicate; recover native/body/root evidence, bind published work and custody, and release only through the original identity. Do not rebuild already accepted work. |
| Collaboration genesis | 1 | Landed #1778 and existing platform owner | Recover the missing capsule/rollout and reconcile original lineage, custody and current owner. Prepared does not mean a repository was created. Any creation consumes the existing named genesis lever/receipt plus fresh absence proof. |
| S15 recovery continuation | 1 | #1571 / landed #1573 | Recover the missing capsule/rollout; reconcile every original campaign leaf, lineage and custody. #1573 preserved continuity; the historical eight-hour deadline is expired and grants no current execution authority. |
| OpenCode closeout sibling | 1 | Existing Limen/Domus receipt owner; Domus #547 | Reconcile multi-repo roots, positive process ownership and retained credential/package/runtime obligations; satisfy complete custody and two canonical release checks. |
| TOTAL | 25 | #3173 reconciliation, original owners retained | Every exact identity and original acceptance remains represented. |

The AV publication/execution denominator is all 15 projects: TMB, hole-loop, SIMVLTANEA, Danse Macabre, OGOD, mavsoleum-a, etc, backwards-up-hill, cycles, noonlight, NRCSVS, NVDE, passing-thru, wrvng-v and God's Ears. Consume the existing full first-packet definitions; do not replace them with a shorter selection.

Closed dependency issues #3145/#3175 are read as existing completed remediation; do not reopen or rerun unchanged passing audits merely to manufacture activity. Witness-access #3003 remains a credential-owner gate: authenticate the intended secret through its owning procedure and observe the implicated witness-contract success. Do not replace, omit or waive the intended witness capability.

Output: original owner receipts proving task predicates, or a specific still-open failed/unmeasured/human gate. Finishing one owner does not close unrelated atoms. Only the human closes permanent atoms.

### T6 - Reach canonical release per exact native session

Owners: original session receipts; #3173 aggregates only.

- [ ] Use the completed existing producer to derive v1/v2 receipts from exact native identity, original anchor, all original scopes, published subject heads, owned/retained paths, committed verification and custody evidence.
- [ ] Resolve broker/worktree mismatch through a real native witness and the documented broker_scope_root_id contract where applicable. Never re-register under another principal or use a child checkout as a replacement native anchor.
- [ ] Take fresh scope/lineage process observations. Reconcile unknown ownership with positive evidence or allow positively owned processes to finish cooperatively. Never kill protected/foreign sessions or exempt a daemon tree.
- [ ] Publish receipt/evidence before release checking. Bind private paths only through opaque IDs/path hashes in tracked records.
- [ ] Run the canonical installed no-tasks-on-me.sh with the original ID/anchor and explicit scopes twice. Both must exit 0 with stable semantic results and no newly created files, leases, runs, worktrees or owners. Exit 1 is remaining measured work; exit 2 is unmeasured.
- [ ] Record task completion and handoff independently. Every retained unfinished object must have its already established open owner; a handoff cannot turn task_acceptance into pass.

Output: two canonical checks for each eligible original session and a derived aggregate with no omitted scopes. Missing original-root/custody/native evidence continues to block affected releases.

### T7 - Archive, reclaim safely and prove the aggregate

Owners: native API, existing branch/worktree reclaimers and #3173.

- [ ] Archive only eligible released sessions through the native API; read back every changed exact ID. Existing 21 archive flags are observations, not retrospective release evidence. Do not attribute unknown historical actors.
- [ ] Recheck the six previously reaped local branches remain absent; add no new deletion count without a new exact receipt.
- [ ] Use current dry-run reclaimer output and explicit allowlists for inactive disposable state only after publication, processes, full custody, dependency and review-closure proof. Retain dirty/active/private/unbacked and absent-volume state.
- [ ] Emit the T2 retirement packet for each newly retired native-session scope in that declared action class; verify absence after execution and an unchanged second pass. Other generated-residue classes keep their existing contracts and never count as original-scope retirement proof.
- [ ] Render the final report from one identified census generation: all 25 identities, archive/release/task acceptance separately, per-surface target vector, complete custody, action actor/counts and retained dispositions. Include this coordinator's independent work/receipt disposition without inflating the screenshot denominator.

Output: an evidence-backed terminal aggregate. Full task completion is claimed only when every original hard predicate passes. A fully homed unresolved gap is a durable checkpoint, not full completion.

## Verification and review focus

| Failure/input class | Owning package and decisive negative control |
|---|---|
| Stale or conflicting observations; unknown remaining allowance | T0/T1: cached no-probe sample or non-exhaustive usage cannot admit heavy/implementation work. |
| Missing root, missing native body, changed candidate bytes | T3/T6: omission, reconstruction resemblance and archive flags never satisfy original identity/custody. |
| Unknown process ownership, PID reuse, wrong principal | T2/T4/T6: no basename exemption or generic-token fallback; identity mismatch blocks. |
| Unavailable contention/custody producer or arbitrary assertion | T2: destructive adoption/release fails closed at that dimension; legacy evidence is not silently upgraded. |
| Runtime drift, partial deployment or missing physical/browser acceptance | T4/T5: source passes cannot set observed task acceptance; retained browser prohibition remains in force. |

For implementation, resolve the gate interpreter once and run the exact focused registry entries. Relevant existing suites include host/inventory admission, sync-release/contention, process ownership/native helpers, closeout/scoped closeout/portable custody, scope retirement/native capture/equivalence, reclaimer, Worker conduct/record-store, and Domus config/ownership/launcher/terminal tests. Domus phase-skill source targets are dot_agents/skills/s-02-plan/SKILL.md, dot_agents/skills/s-03-branch/SKILL.md and dot_agents/skills/s-04-code/SKILL.md; launcher targets are dot_local/libexec/domus-agent-runtime.py and dot_local/bin/executable_domus-process-ownership. Confirm these owning paths and their exact current hashes before mutation. Add only missing behavioral regressions; avoid tests mirroring reversible prose.

Run verify-scoped.sh once on each final implicated tree under the existing batch deadline. Save exact command, own exit code, subject head, input/environment/gate fingerprints and evidence digest. Remote CI availability is distinct from local correctness; never poll or restart unchanged green gates. Live integration/deployment/device checks run when implicated and do not reuse stale observations.

Plan validation: original group counts sum to 25; every reported gap maps to T0-T7 and an existing owner; original acceptance and human gates retained; file paths and plan-chain declaration checked; no claim of implementation or release. Review the draft as an unfamiliar executor before publication.

## Premortem

Sympathetic: merged repairs, existing native census, gate registry, source ownership and portable custody validators provide a substantial reusable base. The plan targets missing proof production and actual owner acceptance rather than rebuilding those systems.

Adversarial:
1. New implementation outruns preservation or collides with another writer. Mitigation: T0/T1 admission and positive claims; one recovery writer; private capture before mutation; exact retained disposition.
2. A permissive producer or legacy flag yields a false green while original roots remain absent. Mitigation: typed custody, complete original denominator, negative controls and two canonical checks.
3. A moving main, stale sensor or review tail consumes the remaining allowance. Mitigation: freeze each tranche's compatible target vector, verify only implicated changed fingerprints, account cumulative usage and stop/checkpoint on exhaustion without automatic renewal.

Orthogonal: some missing original bytes, metadata, rollout bodies or historical execution observations may no longer exist. Engineering can prevent recurrence and establish a truthful loss record; it cannot guarantee historical recovery. Full success remains conditional on authentic evidence and original acceptance, not a renamed criterion.

## Rollback

Revert a faulty source change with a new governed commit. Preserve prior verified installed CLI/protocol/Worker versions and use their owning rollback rails; confirm migration/fencing compatibility before a Worker rollback. For config, retain a private pre-apply snapshot and reconcile only this lane's delta if the app wrote concurrently. Never reset a shared checkout, overwrite newer app state, restore an old broker database over newer events or delete failed custody partials.

Archive flags are reversible through the native API. Reclamation is separately authorized and requires verified restoration before execution; rollback preparation is not deletion permission. Preserve all failed/interrupted observations and their owner.

## Cross-references and continuation

- Reconciliation owner: https://github.com/4444J99/limen/issues/3173
- Existing census: docs/receipts/session-closeout-census-20261023/
- Prior plan: docs/plans/2026-10-23-suggested-session-closeout.md
- Closeout contract and producer: docs/session-closeout.md; #2977; PR #2988
- Runtime/config/custody: #2848; Domus #535 and private preservation PR #556
- Broker implementation, follow-up and canary: #3117; #3118; #2054; #2165
- Research source and acceptance: #3189; #3067; #3056; source-superseded #3087
- OpenCode native access and retained work: #2961; Domus #547
- Launcher diagnostics/interrupts: Domus #554
- Witness access: #3003; credential-wall #320 and its existing credential-organ owners
- Closed dependency remediation: #3145 and #3175
- Finite recovery, admission, source ownership and PR governance: the binding surfaces above.

First execution move: T0 keeper allowance/claims and source/runtime target refresh, then T1's single admitted checkout. The original missing custody investigation can continue only within valid authority and budget. Publication of this plan is neither an execution lease nor a new autonomous goal.
