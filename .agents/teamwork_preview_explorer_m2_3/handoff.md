# Milestone 2: Worktree Verification Requirements & Acceptance Criteria

**Report Author**: `teamwork_preview_explorer_m2_3`  
**Target Milestone**: Milestone 2 (Worktree Isolation & Topic Branch Setup)  
**Working Directory**: `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_m2_3`  
**Target Worktrees Base**: `/Users/4jp/Workspace/.worktrees/`  
**Parent Orchestrator**: `teamwork_preview_orchestrator_m2_worktrees` (`55e92291-a180-416d-8baf-9058f3d8409a`)

---

## 1. Observation

Direct observations from codebase inspection, architectural specifications, and live environment state:

### 1.1 Specification & Scope Directives
- **`ORIGINAL_REQUEST.md §R1` (lines 12–13)**: "Each autonomous lane must operate in its own isolated worktree and topic branch. Drive canonical identity & offer, proof & case-study architecture, and public portfolio/front door to completion with durable receipts."
- **`ORIGINAL_REQUEST.md §Acceptance Criteria` (lines 20–22)**:
  - "Each active lane executes inside a dedicated topic worktree under `/Users/4jp/Workspace/.worktrees/`."
  - "No direct main branch mutations; PRs submitted through canonical conduct/git gates."
- **`SCOPE.md` (lines 4–7, 14–22)**:
  - Defines the 3 required isolated topic worktrees and topic branches:
    1. `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-identity-offer` (branch: `work/psp-omega-lane-identity-offer`)
    2. `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture` (branch: `codex/psp-omega-lane-proof-architecture`)
    3. `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-portfolio-front-door` (branch: `work/psp-omega-lane-portfolio-front-door`)
  - Requires clean worktrees verified against HEAD, intact git worktree backlinks, workstream capsules (`.limen-workstream/`), and zero direct main branch modifications.

### 1.2 Worktree Initialization & Validation Implementation
- **`docs/architecture/worktree-initialization.md` (lines 6–12)**: Details the transactional linked-worktree initialization protocol: staging root creation, exact HEAD/branch/index/tree validation, same-filesystem assertion, atomic rename to final root, bidirectional backlink repair (`gitdir`), and final validation before recording `state=published`.
- **`cli/src/limen/worktree_initialization.py` (lines 118–146)**: `_validate_checkout(path, *, expected_head, branch)` enforces 5 strict git invariants:
  1. HEAD commit matches expected: `git rev-parse HEAD == expected_head`
  2. Branch matches expected: `git symbolic-ref --quiet --short HEAD == branch`
  3. Index tree matches HEAD tree: `git write-tree == git rev-parse HEAD^{tree}`
  4. Index matches HEAD: `git diff --cached --quiet HEAD --` (exit 0)
  5. Working tree matches index: `git diff --quiet --` (exit 0)
  6. Zero untracked files: `git status --porcelain=v1 -z --untracked-files=all` returns empty.
- **`cli/src/limen/worktree_initialization.py` (lines 240–242)**: Atomically writes backlink file `<git_dir>/gitdir` containing `<final_path>/.git\n`.

### 1.3 Direct Main Mutation Prevention Subsystems
- **`scripts/hooks/worktree-commit-guard.sh` (lines 108–126)**:
  - Intercepts tool execution containing `git ... commit`.
  - Derives effective execution directory via `git -C <target>`, preceding `cd <target>`, or session `cwd`.
  - If effective directory resolves to the live repository checkout (`/Users/4jp/Workspace/limen`) AND that checkout is parked on `main`, immediately issues `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",...}}`.
  - Hermetically tested by `scripts/tests/worktree-commit-guard.test.sh` (exit code 0 verified).
- **`scripts/direct-main-writer-audit.py` (lines 94–146)** & **`institutio/governance/direct-main-writers.yaml`**:
  - Scans all 32 production scripts, workflows, and Python CLI modules.
  - Verifies that every Git push, GitHub Contents PUT, and literal main-ref sink is registered and classified.
  - Asserts that `remote_enforcement` specifies `ruleset: limen-default-merge-queue`, `required_rules: [pull_request]`, and `bypass_actors: []`.
  - Ran `python3 scripts/direct-main-writer-audit.py`: output `PASS — 32 classified surfaces; no unclassified production write seam` (exit 0).

### 1.4 Live Repository & Worktree Observations
- In `/Users/4jp/Workspace/.worktrees/`:
  - `limen-psp-omega-lane-proof-architecture` exists at HEAD `77d1069dee4e1c0e80347f5d9e4aea47e334c500` attached to `codex/psp-omega-lane-proof-architecture`.
  - Forward backlink file `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture/.git` points to `/Users/4jp/Workspace/limen/.git/worktrees/limen-psp-omega-lane-proof-architecture`.
  - Reverse backlink file `/Users/4jp/Workspace/limen/.git/worktrees/limen-psp-omega-lane-proof-architecture/gitdir` points to `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture/.git`.
  - Worktree status is 100% clean (`git status --porcelain` is empty).
  - `limen-psp-omega-lane-identity-offer` and `limen-psp-omega-lane-portfolio-front-door` are pending transactional initialization by the Worker.

---

## 2. Logic Chain

From the observed contracts and code to verification requirements:

### 2.1 Logic Chain for Worktree Cleanliness, Branch Attachment, Backlinks, and Invariants (Question 1)
1. **Observation**: `_validate_checkout` in `worktree_initialization.py` requires exact equality between HEAD, index, and working tree, plus exact symbolic ref matching and zero untracked files.
2. **Inference**: A worktree is considered valid and healthy if and only if:
   - It is located at the exact designated path `/Users/4jp/Workspace/.worktrees/<slug>`.
   - `git symbolic-ref --short HEAD` matches its dedicated topic branch (e.g. `work/psp-omega-lane-identity-offer`).
   - `git diff --cached --quiet HEAD` exits 0 (index matches HEAD commit).
   - `git diff --quiet` exits 0 (working tree matches index).
   - `git write-tree` equals `git rev-parse HEAD^{tree}` (index tree hash equals HEAD tree hash).
   - `git status --porcelain=v1 -z --untracked-files=all` returns zero bytes.
3. **Inference (Backlink Integrity)**:
   - Git worktrees require bidirectional pointers between `<worktree>/.git` (containing `gitdir: <common_git>/worktrees/<slug>`) and `<common_git>/worktrees/<slug>/gitdir` (containing `<worktree>/.git\n`).
   - If either pointer is broken or mismatched, `git rev-parse --git-dir` or `git worktree list` fails.
   - Independent verification must verify both the filesystem contents of these two files and the high-level `git rev-parse --path-format=absolute --git-dir` output.

### 2.2 Logic Chain for Preventing Direct Main Mutations (Question 2)
1. **Observation**: `AGENTS.md § Peer Conductor Contract` and `CLAUDE.md § Merge & Branch Protocol` forbid direct commits to `main`.
2. **Observation**: `scripts/hooks/worktree-commit-guard.sh` denies any tool-invoked `git commit` in the live checkout when on `main`.
3. **Observation**: `scripts/direct-main-writer-audit.py` fails closed if any production code contains an unreviewed push to `main`.
4. **Observation**: GitHub remote ruleset requires PRs (`pull_request`) with no bypass actors.
5. **Inference**: Direct main mutation prevention is enforced by a **4-tier Defense Architecture**:
   - **Tier 1 (Protocol Doctrine)**: Agents are instructed to work exclusively in topic branches.
   - **Tier 2 (Hook Interception)**: Mechanical block of `git commit` in live checkout on `main`.
   - **Tier 3 (Static Seam Audit)**: CI/pre-push gate preventing unclassified write seams.
   - **Tier 4 (Remote Ruleset)**: GitHub rejects any non-PR push to `refs/heads/main`.

### 2.3 Logic Chain for Reviewer, Challenger, and Forensic Auditor Roles (Question 3)
1. **Observation**: To guarantee that worktrees are correctly provisioned, non-interfering, and leak-free, verification must be partitioned across complementary, non-overlapping perspectives.
2. **Inference**:
   - **Reviewer 1 (Structural & Git Topology)** verifies the physical directory layout, git worktree list registration, branch attachment, and bidirectional backlinks.
   - **Reviewer 2 (Cleanliness & Capsule Metadata)** verifies that status is clean, index and trees match, capsule files/ignore rules exist, and transactional receipts are published.
   - **Challenger 1 (Adversarial Branch & Mutation Isolation)** attempts/inspects adversarial conditions: confirms live root commit guard blocks, tests branch uniqueness, and validates cross-worktree isolation.
   - **Challenger 2 (Lifecycle, Debt & Recovery Stress)** validates worktree debt posture, runs `direct-main-writer-audit.py`, tests `git worktree repair` idempotence, and ensures no orphan staging directories.
   - **Forensic Auditor (Gate Verdict & Cryptographic Trail)** collates raw command execution logs, verifies commit SHAs, validates 100% adherence to acceptance criteria, and issues the formal gate verdict in `GATE_STATUS.md`.

---

## 3. Caveats

1. **Active Live Sessions**: The live environment contains active worktrees from other background runs (e.g. Jules, overnight watch). Verification commands must target only the three PSP Omega topic worktrees under `/Users/4jp/Workspace/.worktrees/` and must not disturb unrelated active worktrees.
2. **Pre-existing Worktree**: `limen-psp-omega-lane-proof-architecture` already exists and was found in a clean state. Worker should verify and reuse it (or refresh if needed) while creating the remaining two worktrees.
3. **Disk Space Admission**: Worktree creation respects the local disk capacity floor (~20 GiB required free). Current scratch/workspace partition has ample room.

---

## 4. Conclusion & Synthesis

### 4.1 Verification Matrix for Worker & Verifiers

| Invariant / Check | Target Scope | Command / Check Method | Expected Output / Exit Code | Assigned Verifier |
|---|---|---|---|---|
| **WT-01: Directory Presence & Paths** | All 3 Worktrees | `test -d /Users/4jp/Workspace/.worktrees/<slug>` | Exit code `0` | Worker, Reviewer 1, Auditor |
| **WT-02: Worktree Registry** | Repo Root | `git worktree list --porcelain` | Lists all 3 worktree paths with their respective branches | Reviewer 1, Auditor |
| **WT-03: Branch Attachment** | Lane 1 (`identity-offer`) | `git -C /Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-identity-offer symbolic-ref --short HEAD` | `work/psp-omega-lane-identity-offer` (Exit 0) | Reviewer 1, Auditor |
| **WT-04: Branch Attachment** | Lane 2 (`proof-architecture`) | `git -C /Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture symbolic-ref --short HEAD` | `codex/psp-omega-lane-proof-architecture` (Exit 0) | Reviewer 1, Auditor |
| **WT-05: Branch Attachment** | Lane 3 (`portfolio-front-door`) | `git -C /Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-portfolio-front-door symbolic-ref --short HEAD` | `work/psp-omega-lane-portfolio-front-door` (Exit 0) | Reviewer 1, Auditor |
| **WT-06: Bidirectional Backlinks** | All 3 Worktrees | `cat <wt>/.git` and `cat <repo>/.git/worktrees/<slug>/gitdir` | `<wt>/.git` points to `<repo>/.git/worktrees/<slug>`; `<repo>/.git/worktrees/<slug>/gitdir` points to `<wt>/.git` | Reviewer 1, Auditor |
| **WT-07: Git Resolution Parity** | All 3 Worktrees | `git -C <wt> rev-parse --path-format=absolute --git-dir` and `--git-common-dir` | Resolves to respective `.git/worktrees/<slug>` and common `.git` dir | Reviewer 1, Auditor |
| **WT-08: Working Tree Cleanliness** | All 3 Worktrees | `git -C <wt> status --porcelain=v1 -z --untracked-files=all` | Empty string (Exit 0) | Reviewer 2, Auditor |
| **WT-09: Index-to-HEAD Parity** | All 3 Worktrees | `git -C <wt> diff --cached --quiet HEAD --` | Exit code `0` | Reviewer 2, Auditor |
| **WT-10: Tree-to-Index Parity** | All 3 Worktrees | `git -C <wt> diff --quiet --` | Exit code `0` | Reviewer 2, Auditor |
| **WT-11: Tree Hash Parity** | All 3 Worktrees | `[ "$(git -C <wt> write-tree)" = "$(git -C <wt> rev-parse HEAD^{tree})" ]` | Evaluates to True (Exit 0) | Reviewer 2, Auditor |
| **WT-12: Ignore Rule Parity** | Repo Root | `git -C /Users/4jp/Workspace/limen check-ignore -v /Users/4jp/Workspace/.worktrees/` | Matches exclude rule in `.git/info/exclude` | Reviewer 2 |
| **WT-13: Main Commit Guard** | Live Repo Root | `bash scripts/tests/worktree-commit-guard.test.sh` | `worktree-commit-guard.test: ok` (Exit 0) | Challenger 1 |
| **WT-14: Branch Collision & Isolation** | All 3 Worktrees | Assert distinct topic branches; verify none are attached to `main` | Topic branches distinct, non-overlapping with `main` | Challenger 1 |
| **WT-15: Direct Main Writer Audit** | Repo Root | `python3 scripts/direct-main-writer-audit.py` | `PASS — 32 classified surfaces; no unclassified production write seam` (Exit 0) | Challenger 2 |
| **WT-16: Staging Residue Check** | Worktrees Base | `find /Users/4jp/Workspace/.worktrees/ -maxdepth 1 -name ".limen-init-*"` | Empty (no crashed/unmoved staging roots) | Challenger 2 |
| **WT-17: End-to-End Cryptographic Audit** | All 3 Worktrees | Validate HEAD commit hashes against origin base, collate all exit codes | All exit codes `0`, receipts compiled into `GATE_STATUS.md` | Forensic Auditor |

---

### 4.2 Verifier Action Checklists

#### Worker Checklist
- [ ] Initialize Lane 1: `limen-psp-omega-lane-identity-offer` on `work/psp-omega-lane-identity-offer` under `/Users/4jp/Workspace/.worktrees/`.
- [ ] Initialize/Verify Lane 2: `limen-psp-omega-lane-proof-architecture` on `codex/psp-omega-lane-proof-architecture` under `/Users/4jp/Workspace/.worktrees/`.
- [ ] Initialize Lane 3: `limen-psp-omega-lane-portfolio-front-door` on `work/psp-omega-lane-portfolio-front-door` under `/Users/4jp/Workspace/.worktrees/`.
- [ ] Verify each worktree satisfies `status --porcelain == ""` and `diff --cached --quiet HEAD`.
- [ ] Verify `.git/info/exclude` has `.worktrees/` and `.limen-workstream/`.
- [ ] Document all paths, branches, and commit SHAs in `handoff.md`.

#### Reviewer 1 Checklist (Topology & Backlinks)
- [ ] Verify `WT-01`: Physical paths exist under `/Users/4jp/Workspace/.worktrees/`.
- [ ] Verify `WT-02`: `git worktree list --porcelain` in main repo includes all 3 lanes.
- [ ] Verify `WT-03`, `WT-04`, `WT-05`: Branch names match exact specifications.
- [ ] Verify `WT-06`: Forward `.git` and reverse `gitdir` backlinks resolve bidirectionally.
- [ ] Verify `WT-07`: `git rev-parse --git-dir` and `--git-common-dir` resolve properly.

#### Reviewer 2 Checklist (Cleanliness & Capsules)
- [ ] Verify `WT-08`: `git status --porcelain=v1 -z` returns 0 output for all 3 worktrees.
- [ ] Verify `WT-09`: `git diff --cached --quiet HEAD` exits 0 for all 3 worktrees.
- [ ] Verify `WT-10`: `git diff --quiet` exits 0 for all 3 worktrees.
- [ ] Verify `WT-11`: `write-tree` equals `HEAD^{tree}` for all 3 worktrees.
- [ ] Verify `WT-12`: `.git/info/exclude` properly configured.

#### Challenger 1 Checklist (Adversarial Branch & Mutation Isolation)
- [ ] Verify `WT-13`: Run `bash scripts/tests/worktree-commit-guard.test.sh` (must pass).
- [ ] Verify `WT-14`: Assert that all 3 topic branches are strictly distinct and none are on `main`.
- [ ] Verify that pushing from each worktree targets only its dedicated topic branch.
- [ ] Verify that index operations in one worktree do not lock or taint sibling worktrees.

#### Challenger 2 Checklist (Worktree Lifecycle & Seam Audit)
- [ ] Verify `WT-15`: Run `python3 scripts/direct-main-writer-audit.py` (must pass with 0 unclassified seams).
- [ ] Verify `WT-16`: Verify absence of any lingering `.limen-init-*` staging directories.
- [ ] Verify `git worktree repair` runs cleanly and idempotently across all 3 worktrees.

#### Forensic Auditor Checklist (Gate Verdict)
- [ ] Verify `WT-17`: Complete end-to-end command execution and exit code recording (`EXIT=0`).
- [ ] Verify exact HEAD commit SHAs across all 3 worktrees match expected base commit.
- [ ] Confirm all Reviewer and Challenger reports are positive with zero defects.
- [ ] Author definitive `GATE_STATUS.md` with `PASSED` verdict and emit terminal audit receipt.

---

## 5. Verification Method

To independently verify all findings and test commands in this report:

1. **Verify Commit Guard & Direct Main Writer Audit**:
   ```bash
   bash scripts/tests/worktree-commit-guard.test.sh
   python3 scripts/direct-main-writer-audit.py
   ```
2. **Verify Worktree Status & Invariants on Any Established Worktree**:
   ```bash
   WT="/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture"
   git -C "$WT" rev-parse --is-inside-work-tree
   git -C "$WT" symbolic-ref --short HEAD
   git -C "$WT" diff --cached --quiet HEAD --
   git -C "$WT" diff --quiet --
   git -C "$WT" status --porcelain=v1 -z --untracked-files=all
   test -f "$WT/.git"
   ```
3. **Verify Git Backlinks**:
   ```bash
   WT="/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture"
   cat "$WT/.git"
   cat "/Users/4jp/Workspace/limen/.git/worktrees/$(basename "$WT")/gitdir"
   ```

**Invalidation Conditions**:
- A commit occurs directly on `main` in the live checkout.
- A topic worktree is attached to an incorrect branch name.
- A worktree contains uncommitted index changes or untracked dirty files.
- Forward or reverse `gitdir` backlinks point to non-existent paths.
