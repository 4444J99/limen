# Original User Request

## 2026-08-19T15:05:25Z

<USER_REQUEST>
Advance the VLTIMA 5-primitive kernel mapping across the ecosystem, authoring the first working vertical slice and schema validation for the Representation Organ, and implementing the autonomous self-feeding observation loop for the Observation Organ.

Working directory: /Users/4jp/Workspace/limen
Integrity mode: development

## Requirements

### R1. Representation Organ Vertical Slice & Validation
Map the 5-primitive kernel (Member · Mandate · Standing · Standard · Governance) to the Representation Organ domain. Implement and verify the career and opportunity intake pipeline (organs/representation/), ensuring opportunity ingestion, packet generation, and validate-representation.py execute deterministically.

### R2. Observation Organ Autonomous Self-Feed Loop
Operationalize the Observation Organ (organs/observation/) by wiring the Bifrons telemetry collectors, observation feed intake, and automated state emission loops so the organ continuously observes and records system vitals without manual prompting.

### R3. Multi-Agent Worktree Isolation & Concurrency
Ensure all changes adhere to Limen's Peer Conductor Contract and machine-wide host admission protocol, maintaining decoupled worktree isolation and lossless git tracking.

## Acceptance Criteria

### Objective Verification
- [ ] python3 organs/representation/validate-representation.py passes with EXIT=0.
- [ ] Observation telemetry collector emits valid schema-checked observations to its feed.
- [ ] scripts/verify-scoped.sh passes with EXIT=0 on all modified paths.
- [ ] python3 scripts/check-agent-docs.py passes with EXIT=0.
- [ ] scripts/no-tasks-on-me.sh and python3 scripts/credential-wall.py --check pass with EXIT=0.
## 2026-08-20T18:59:21Z

<USER_REQUEST>
Continuously tend, verify, and land all outstanding and unmerged remote workstreams into `organvm/limen`'s `main` branch, ensuring 100% test integrity and reducing the active remote and local branch estate down to `main` without touching `/Users/4jp/Workspace/hospes`.

Working directory: /Users/4jp/Workspace/limen
Integrity mode: development

## Requirements

### R1. PR #2520 Final Landing & Integration
- Monitor and ensure PR #2520 (land all continuation capsules, prima materia universe, and notifier pipelines) passes all GitHub CI checks and merges cleanly into `main`.
- Pull merged `main` locally.

### R2. Automated Lossless Branch Reaping
- Execute `LIMEN_REMOTE_REAP_APPLY=1 python3 scripts/reap-remote-branches.py` to prune remote refs whose commits are now in `main`.
- Execute `python3 scripts/reap-branches.py --apply` to clean up local squash-merged branch refs.

### R3. Comprehensive Unmerged Remote Tail Reconciliation
- For any remaining unlanded remote branches:
  1. Inspect the diff against `origin/main`.
  2. Rebase onto latest `main` and resolve any merge conflicts.
  3. Run `scripts/verify-scoped.sh` and targeted pytest/lint gates to ensure green CI.
  4. Submit and merge via PR, preserving all commit authorship and work history.
  5. Prune the remote tracking ref once safely landed.

### R4. Ecosystem Invariants & Host Discipline
- Respect host admission invariants (at most one heavy runner machine-wide).
- Maintain 100% pass on all documentation, manifest, and credential checks (`check-agent-docs.py`, `credential-wall.py --check`, `no-tasks-on-me.sh`).

## Acceptance Criteria

### Objective Verification
- [ ] PR #2520 successfully merged into `main`.
- [ ] Remote branch count on `origin` is reduced to 1 (`main`) or only active protected refs.
- [ ] `python3 scripts/check-agent-docs.py` passes with `EXIT=0`.
- [ ] `scripts/no-tasks-on-me.sh` and `python3 scripts/credential-wall.py --check` pass with `EXIT=0`.
- [ ] Zero unmerged or unpreserved code lost across the entire estate.

</USER_REQUEST>
